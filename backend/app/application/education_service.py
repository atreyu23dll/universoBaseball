"""Catálogo territorial de instituciones educativas reales.

El catálogo vive en la base, importado del fichero versionado que acompaña al
repositorio (`data/universities/`). **Este módulo no hace peticiones de red**:
ni al consultar un territorio, ni al crear una liga, ni al generar una edición.
Lo que encuentre se congela en el reglamento que el usuario previsualiza, con
su fuente e identificador externo, para que la edición sea reproducible.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.application.errors import TypedValidationFailure
from app.infrastructure import models as m
from simulation.competitions.ruleset import (
    MAX_CLUBS_PER_COMPETITION,
    RuleSet,
    Scope,
    UniversityParticipant,
)
from simulation.geography.distance import haversine_km

SOURCE_ATTRIBUTION = (
    "Wikidata (https://www.wikidata.org), CC0 1.0 — instituciones; "
    "GeoNames (https://www.geonames.org), CC BY 4.0 — localidades que las sitúan"
)
MUNICIPAL_RADIUS_KM = 90.0
#: Un grado de latitud son unos 111 km. El recuadro previo a la distancia
#: exacta evita traer de la base las instituciones del otro extremo del país.
KM_PER_DEGREE = 111.0


def catalog_status(session: Session) -> dict[str, Any]:
    total = session.scalar(select(func.count()).select_from(m.EducationalInstitution)) or 0
    sources = session.scalars(
        select(m.EducationalInstitution.source).distinct().order_by(m.EducationalInstitution.source)
    ).all()
    return {
        "available": bool(total),
        "institutions": total,
        "sources": list(sources),
        "attribution": SOURCE_ATTRIBUTION,
        "note": (
            "Catálogo de universidades reales disponible para la consulta territorial."
            if total
            else "No hay catálogo universitario importado. Ejecuta `make import-universities`, "
            "que lee el fichero versionado del repositorio y no descarga nada."
        ),
    }


def discover_universities(
    session: Session, universe_id: str, raw_scope: dict[str, Any]
) -> dict[str, Any]:
    """Devuelve todas las universidades del catálogo que caen en el territorio.

    Para países y provincias se usa la división administrativa que el
    importador resolvió contra el gazetteer, no la que declare la fuente
    educativa, que es irregular. En territorio municipal, donde no hay
    polígonos de campus, se declara un radio de 90 km desde la localidad
    elegida en vez de fingir una frontera exacta.
    """
    try:
        scope = Scope.model_validate(raw_scope)
    except Exception as exc:
        raise TypedValidationFailure(
            "EDUCATION_TERRITORY_INVALID",
            f"no se pudo consultar universidades para ese territorio: {exc}",
        ) from exc

    status = catalog_status(session)
    if not status["available"]:
        return {
            **status,
            "status": "catalog_not_imported",
            "scope_level": str(scope.level),
            "territory_mode": "not_evaluated",
            "found": 0,
            "institutions": [],
        }

    rows, territory_mode = _universities_for_scope(session, universe_id, scope)
    if len(rows) > MAX_CLUBS_PER_COMPETITION:
        # Desde que el catálogo cubre el mundo de verdad, un país entero puede
        # tener cientos de instituciones. Caben todas en la respuesta —para que
        # se vea qué hay— pero no en una liga, y se dice antes de intentarlo.
        return {
            **status,
            "status": "territory_too_large",
            "scope_level": str(scope.level),
            "territory_mode": territory_mode,
            "found": len(rows),
            # No se devuelven las fichas: son cientos y no sirven para armar
            # esta liga. Lo que hace falta saber es cuántas hay y que sobran.
            "institutions": [],
            "note": (
                f"El territorio tiene {len(rows)} instituciones reales y una competición "
                f"admite {MAX_CLUBS_PER_COMPETITION} equipos como mucho. Acota el territorio "
                "—una provincia o un municipio— en vez de recortar la lista: una liga escolar "
                "juega con todas las del territorio, no con una selección."
            ),
        }
    return {
        **status,
        "status": "ready",
        "scope_level": str(scope.level),
        "territory_mode": territory_mode,
        "found": len(rows),
        "institutions": [_brief(row) for row in rows],
        "note": (
            f"Se encontraron {len(rows)} institución(es) reales de educación superior. "
            "Esta liga jugará con ese conjunto exacto; el motor no añadirá equipos aleatorios."
            if rows
            else "No hay instituciones del catálogo dentro del territorio resuelto. "
            "Amplía o corrige el territorio; no se crearán equipos ficticios para completar la liga."
        ),
    }


def canonicalize_school_universities(
    session: Session, universe_id: str, ruleset: RuleSet
) -> RuleSet:
    """Comprueba y congela el conjunto que verá una liga escolar adulta."""
    if not ruleset.requires_real_universities:
        return ruleset

    assert ruleset.education is not None
    discovered, _ = _universities_for_scope(session, universe_id, ruleset.scope)
    expected = {row.id: row for row in discovered}
    submitted = {item.catalog_id for item in ruleset.education.universities}
    if not expected:
        raise TypedValidationFailure(
            "EDUCATION_INSTITUTIONS_UNAVAILABLE",
            "no hay universidades reales disponibles en el territorio de esta liga escolar adulta",
            [
                "amplía o cambia el territorio",
                "si el catálogo no está importado, ejecuta `make import-universities`",
            ],
        )
    if submitted != set(expected):
        raise TypedValidationFailure(
            "EDUCATION_CATALOG_MISMATCH",
            "la lista de universidades cambió o no corresponde al territorio resuelto",
            [
                "vuelve al paso de participantes y consulta de nuevo las universidades",
                "la liga debe incluir exactamente todas las instituciones encontradas",
            ],
        )

    # Conservamos el orden territorial estable que vio el usuario (país,
    # nombre, id), no el orden accidental de los UUID de la base.
    canonical = [_participant(row) for row in discovered]
    education = ruleset.education.model_copy(update={"universities": canonical})
    # El validador de RuleSet ya comprobó que el contador coincide; copiar los
    # valores canónicos no cambia su tamaño y deja el snapshot confiable.
    return ruleset.model_copy(update={"education": education})


def _universities_for_scope(
    session: Session, universe_id: str, scope: Scope
) -> tuple[list[m.EducationalInstitution], str]:
    """Las instituciones del catálogo que caen dentro de un territorio.

    Nunca se trae el catálogo entero a memoria: son decenas de miles de filas
    y el territorio siempre acota por país. Lo que no se puede resolver en SQL
    —la distancia exacta a una localidad— se calcula sobre ese recorte.
    """
    countries: set[str] = set()
    regions: set[tuple[str, str]] = set()
    centers: list[tuple[float, float]] = []

    if scope.entity_ids:
        entities = [session.get(m.GazetteerEntity, entity_id) for entity_id in scope.entity_ids]
        if any(entity is None for entity in entities):
            raise TypedValidationFailure(
                "EDUCATION_TERRITORY_INVALID",
                "una entidad del territorio no existe en el gazetteer",
            )
        for entity in entities:
            assert entity is not None
            countries.add(entity.country_iso2)
            if scope.level.value == "regional" and entity.admin1_code:
                regions.add((entity.country_iso2, entity.admin1_code))
            if scope.level.value == "municipal":
                centers.append((entity.lat, entity.lon))
        if scope.mode.value == "radius":
            center = entities[0]
            assert center is not None
            radius = scope.radius_km or MUNICIPAL_RADIUS_KM
            return _within_radius(
                session, [(center.lat, center.lon)], radius, countries
            ), f"radio declarado de {radius:g} km"
    else:
        places = session.scalars(
            select(m.Place).where(
                m.Place.universe_id == universe_id,
                m.Place.place_key.in_(scope.place_keys),
            )
        ).all()
        if len(places) != len(scope.place_keys):
            raise TypedValidationFailure(
                "EDUCATION_TERRITORY_INVALID",
                "el territorio debe resolverse antes de consultar universidades",
            )
        for place in places:
            countries.add(place.country_code)
            if scope.level.value == "municipal":
                centers.append((place.lat, place.lon))

    if scope.level.value == "municipal" and centers:
        return _within_radius(session, centers, MUNICIPAL_RADIUS_KM, countries), (
            f"radio declarado de {MUNICIPAL_RADIUS_KM:g} km desde la localidad"
        )
    if scope.level.value == "regional" and regions:
        condicion = or_(
            *[
                (m.EducationalInstitution.country_iso2 == iso2)
                & (m.EducationalInstitution.admin1_code == admin1)
                for iso2, admin1 in sorted(regions)
            ]
        )
        return _sorted(
            session.scalars(select(m.EducationalInstitution).where(condicion)).all()
        ), "división administrativa de primer nivel"

    if scope.country_code:
        countries.add(scope.country_code.upper())
    if not countries:
        return [], "territorio sin país resuelto"
    return _sorted(
        session.scalars(
            select(m.EducationalInstitution).where(
                m.EducationalInstitution.country_iso2.in_(sorted(countries))
            )
        ).all()
    ), "país(es) del territorio"


def _within_radius(
    session: Session,
    centers: list[tuple[float, float]],
    radius_km: float,
    allowed_countries: set[str],
) -> list[m.EducationalInstitution]:
    """Instituciones a menos de `radius_km` de alguna de las localidades.

    La base acota por país y por banda de latitud —que no se rompe al cruzar
    el antimeridiano, cosa que una banda de longitud sí haría— y la distancia
    exacta se mide ya sobre ese recorte.
    """
    if not centers or not allowed_countries:
        return []
    margen = radius_km / KM_PER_DEGREE
    bandas = or_(
        *[m.EducationalInstitution.lat.between(lat - margen, lat + margen) for lat, _ in centers]
    )
    candidatas = session.scalars(
        select(m.EducationalInstitution).where(
            m.EducationalInstitution.country_iso2.in_(sorted(allowed_countries)),
            bandas,
        )
    ).all()
    return _sorted(
        [
            fila
            for fila in candidatas
            if any(haversine_km(lat, lon, fila.lat, fila.lon) <= radius_km for lat, lon in centers)
        ]
    )


def _sorted(rows: list[m.EducationalInstitution]) -> list[m.EducationalInstitution]:
    return sorted(rows, key=lambda row: (row.country_iso2, row.name.casefold(), row.id))


def _participant(row: m.EducationalInstitution) -> UniversityParticipant:
    return UniversityParticipant(
        catalog_id=row.id,
        source=row.source,
        source_id=row.source_id,
        name=row.name,
        country_code=row.country_iso2,
        admin1_code=row.admin1_code,
        admin2_code=row.admin2_code,
        lat=row.lat,
        lon=row.lon,
        timezone=row.timezone,
        institution_type=row.institution_type,
        locality_name=row.locality_name,
        founded_year=row.founded_year,
    )


def _brief(row: m.EducationalInstitution) -> dict[str, Any]:
    return _participant(row).model_dump(mode="json") | {
        "source_url": row.source_url,
        "licence": row.licence,
        "website": row.website,
    }
