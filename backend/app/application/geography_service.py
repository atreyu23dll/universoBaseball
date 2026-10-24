"""Resolución geográfica: buscar un lugar del mundo y fijarlo sin ambigüedad.

El FIX V2 de Fase 1 (§4.2) lo dice sin rodeos: «`Kampala` es una etiqueta, no
una identidad geográfica». Este módulo implementa la diferencia:

```text
unresolved  →  candidates  →  user_selected  →  verified | incomplete
```

Una búsqueda devuelve **candidatos** con su país, su jerarquía, su tipo de
entidad y su identificador estable. El usuario elige uno, y a partir de ahí la
competición guarda ese identificador, no un texto. Un nombre sin resolver no
puede poner en marcha una generación que presuma ser contextual: eso devuelve
`GEOGRAPHY_UNRESOLVED`.

Lo que **no** hace: inventar resultados. Si no hay coincidencias, dice que no
hay; nunca sustituye en silencio una búsqueda fallida por opciones
predefinidas, que es justo el defecto que había que corregir.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.application.errors import NotFoundError, TypedValidationFailure
from app.infrastructure import models as m
from simulation.geography.distance import haversine_km
from simulation.geography.geonames import ATTRIBUTION, normalize

#: Orden de preferencia de los tipos de entidad al desambiguar: si alguien
#: escribe «México» quiere el país antes que la ciudad homónima.
KIND_RANK = {"country": 0, "region": 1, "city": 2, "district": 3}

#: Cuántos candidatos se devuelven como máximo. Un buscador que devuelve
#: doscientas filas no desambigua nada.
MAX_RESULTS = 25


class GeographyUnresolved(TypedValidationFailure):
    def __init__(self, message: str, suggestions: list[str] | None = None) -> None:
        super().__init__("GEOGRAPHY_UNRESOLVED", message, suggestions)


class GeographyAmbiguous(TypedValidationFailure):
    def __init__(self, message: str, suggestions: list[str] | None = None) -> None:
        super().__init__("GEOGRAPHY_AMBIGUOUS", message, suggestions)


class GeographyBoundaryMissing(TypedValidationFailure):
    def __init__(self, message: str, suggestions: list[str] | None = None) -> None:
        super().__init__("GEOGRAPHY_BOUNDARY_MISSING", message, suggestions)


@dataclass(frozen=True)
class GazetteerStatus:
    """Si hay gazetteer importado y qué cubre."""

    countries: int
    entities: int
    with_currency: int
    with_reference_cost: int

    @property
    def imported(self) -> bool:
        return self.entities > 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "imported": self.imported,
            "countries": self.countries,
            "entities": self.entities,
            "countries_with_currency": self.with_currency,
            "countries_with_reference_cost": self.with_reference_cost,
            "attribution": ATTRIBUTION,
            "note": (
                "Búsqueda mundial sobre el gazetteer importado."
                if self.imported
                else "No hay gazetteer importado: ejecuta `make import-geonames`. "
                "Sin él no se puede resolver ningún territorio del mundo y el "
                "asistente solo ofrece el fixture curado."
            ),
        }


def gazetteer_status(session: Session) -> GazetteerStatus:
    return GazetteerStatus(
        countries=session.scalar(select(func.count()).select_from(m.GazetteerCountry)) or 0,
        entities=session.scalar(select(func.count()).select_from(m.GazetteerEntity)) or 0,
        with_currency=session.scalar(
            select(func.count())
            .select_from(m.GazetteerCountry)
            .where(m.GazetteerCountry.currency_code.is_not(None))
        )
        or 0,
        with_reference_cost=session.scalar(
            select(func.count())
            .select_from(m.GazetteerCountry)
            .where(m.GazetteerCountry.reference_monthly_cost.is_not(None))
        )
        or 0,
    )


def search(
    session: Session,
    query: str,
    limit: int = 10,
    country: str | None = None,
    kind: str | None = None,
    min_population: int = 0,
) -> dict[str, Any]:
    """Busca un lugar por nombre o variante y devuelve candidatos desambiguados."""
    texto = normalize(query.strip())
    if len(texto) < 2:
        raise GeographyUnresolved(
            "la búsqueda geográfica necesita al menos dos caracteres",
            ["escribe el nombre de una localidad, región o país"],
        )

    estado = gazetteer_status(session)
    if not estado.imported:
        raise GeographyUnresolved(
            "no hay gazetteer importado: no se puede resolver ningún territorio",
            [
                "ejecuta `make import-geonames` para importar GeoNames",
                "o `python scripts/import_geonames.py --source-dir data/gazetteer/sample` "
                "para el extracto de prueba",
            ],
        )

    condiciones = [
        or_(
            m.GazetteerEntity.search_text.like(f"{texto}%"),
            m.GazetteerEntity.search_text.like(f"%|{texto}%"),
            m.GazetteerEntity.search_text.like(f"% {texto}%"),
        )
    ]
    if country:
        condiciones.append(m.GazetteerEntity.country_iso2 == country.strip().upper())
    if kind:
        condiciones.append(m.GazetteerEntity.kind == kind.strip().lower())
    if min_population:
        condiciones.append(m.GazetteerEntity.population >= min_population)

    filas = session.scalars(
        select(m.GazetteerEntity)
        .where(*condiciones)
        .order_by(m.GazetteerEntity.population.desc())
        .limit(min(max(1, limit), MAX_RESULTS) * 4)
    ).all()

    # Reordenación: primero lo que coincide por nombre exacto, después por tipo
    # de entidad y población. Así «Kampala» devuelve la capital de Uganda y no
    # un barrio homónimo de otro continente.
    def rango(fila: m.GazetteerEntity) -> tuple:
        nombre = normalize(fila.name)
        exacto = 0 if nombre == texto else (1 if nombre.startswith(texto) else 2)
        return (exacto, KIND_RANK.get(fila.kind, 9), -fila.population, fila.name)

    ordenadas = sorted(filas, key=rango)[: min(max(1, limit), MAX_RESULTS)]
    paises = _countries_by_iso(session, {f.country_iso2 for f in ordenadas})

    return {
        "query": query,
        "normalized": texto,
        "status": "candidates" if ordenadas else "unresolved",
        "total": len(ordenadas),
        "items": [
            _entity_brief(session, fila, paises.get(fila.country_iso2)) for fila in ordenadas
        ],
        "attribution": ATTRIBUTION,
        "note": (
            "Elige una entidad para fijar el territorio: la competición guardará "
            "su identificador, no el texto que escribiste."
            if ordenadas
            else "Sin coincidencias en el gazetteer. No se sustituye por opciones "
            "predefinidas: prueba otro nombre, otra variante o filtra por país."
        ),
    }


def get_entity(session: Session, entity_id: str) -> m.GazetteerEntity:
    fila = session.get(m.GazetteerEntity, entity_id)
    if fila is None:
        raise NotFoundError(f"no existe la entidad geográfica {entity_id}")
    return fila


def entity_detail(session: Session, entity_id: str) -> dict[str, Any]:
    """Ficha de una entidad: jerarquía, moneda, límite y estado de resolución."""
    fila = get_entity(session, entity_id)
    pais = session.get(m.GazetteerCountry, fila.country_iso2)
    detalle = _entity_brief(session, fila, pais)
    detalle["hierarchy"] = [
        _entity_brief(session, ancestro, pais) for ancestro in _ancestors(session, fila)
    ]
    detalle["boundary"] = _boundary_info(session, fila)
    detalle["currency"] = _currency_info(pais)
    detalle["variants"] = list(fila.variants)
    return detalle


def entity_context(session: Session, entity_id: str) -> dict[str, Any]:
    """Contexto regional de una entidad: lo que se sabe y lo que no.

    Es la respuesta honesta a «¿qué sé de este territorio?»: población con
    fuente, moneda con fuente, y los índices socioeconómicos marcados como
    supuesto declarado cuando no hay evidencia local, nunca inferidos del país.
    """
    fila = get_entity(session, entity_id)
    pais = session.get(m.GazetteerCountry, fila.country_iso2)
    curado = _curated_profile(session, fila)

    descendientes = session.scalar(
        select(func.count())
        .select_from(m.GazetteerEntity)
        .where(m.GazetteerEntity.parent_id == fila.id)
    )
    indices = (
        {
            "economy_index": curado.economy_index,
            "baseball_culture_index": curado.baseball_culture_index,
            "cost_of_living_index": curado.cost_of_living_index,
            "infrastructure_index": curado.infrastructure_index,
            "confidence": curado.confidence,
            "sources": curado.sources,
        }
        if curado is not None
        else {
            "economy_index": 0.5,
            "baseball_culture_index": 0.5,
            "cost_of_living_index": 0.5,
            "infrastructure_index": 0.5,
            "confidence": "scenario_assumption",
            "sources": [
                "sin evidencia local: supuesto neutral declarado",
                "no se infiere del país ni de estereotipos nacionales",
            ],
        }
    )

    return {
        "entity": _entity_brief(session, fila, pais),
        "population": {
            "value": fila.population or None,
            "confidence": "observed" if fila.population else "missing",
            "sources": [ATTRIBUTION, f"geonameid {fila.source_id}"],
        },
        "currency": _currency_info(pais),
        "indices": indices,
        "boundary": _boundary_info(session, fila),
        "children": descendientes or 0,
        "warnings": _context_warnings(fila, pais, curado is not None),
    }


def resolve_custom_area(
    session: Session,
    center_entity_id: str,
    radius_km: float,
    limit: int = 200,
    min_population: int = 0,
) -> dict[str, Any]:
    """Delimita un territorio por **radio** desde una entidad resuelta.

    Es la alternativa que el FIX V2 §4.5 exige ofrecer cuando no hay polígono
    administrativo: en vez de dibujar una frontera inventada, se declara un
    radio desde un punto resuelto y se dice que es una aproximación.
    """
    centro = get_entity(session, center_entity_id)
    if radius_km <= 0 or radius_km > 1500:
        raise TypedValidationFailure(
            "GEOGRAPHY_BOUNDARY_MISSING",
            f"un radio de {radius_km} km no delimita un territorio utilizable",
            ["usa un radio entre 1 y 1500 km"],
        )

    # Primer filtro por caja envolvente en SQL —barato— y después distancia
    # exacta en Python. Sin PostGIS esto es lo correcto: una caja no es un
    # círculo, y se dice qué se hizo.
    grados_lat = radius_km / 111.0
    grados_lon = radius_km / max(1.0, 111.0 * abs(_cos_lat(centro.lat)))
    candidatas = session.scalars(
        select(m.GazetteerEntity)
        .where(
            m.GazetteerEntity.kind.in_(("city", "district")),
            m.GazetteerEntity.lat.between(centro.lat - grados_lat, centro.lat + grados_lat),
            m.GazetteerEntity.lon.between(centro.lon - grados_lon, centro.lon + grados_lon),
            m.GazetteerEntity.population >= min_population,
        )
        .limit(limit * 6)
    ).all()

    dentro = []
    for fila in candidatas:
        distancia = haversine_km(centro.lat, centro.lon, fila.lat, fila.lon)
        if distancia <= radius_km:
            dentro.append((distancia, fila))
    dentro.sort(key=lambda par: (-par[1].population, par[0]))
    dentro = dentro[:limit]

    paises = _countries_by_iso(session, {f.country_iso2 for _, f in dentro})
    return {
        "mode": "radius",
        "status": "user_selected",
        "center": _entity_brief(session, centro, paises.get(centro.country_iso2)),
        "radius_km": radius_km,
        "total": len(dentro),
        "population": sum(f.population for _, f in dentro),
        "countries": sorted({f.country_iso2 for _, f in dentro}),
        "items": [
            {
                **_entity_brief(session, fila, paises.get(fila.country_iso2)),
                "distance_km": round(distancia, 1),
            }
            for distancia, fila in dentro
        ],
        "note": (
            f"Delimitación por radio de {radius_km:g} km desde "
            f"«{centro.name}». Es una **aproximación declarada**, no un límite "
            "administrativo: las distancias son en línea recta sobre la esfera y "
            "no respetan fronteras."
        ),
    }


def resolve_territory(session: Session, entity_ids: list[str]) -> dict[str, Any]:
    """Comprueba que un territorio está resuelto y resume qué se sabe de él.

    Lo llama la creación de competiciones antes de generar nada: sin entidades
    resueltas no hay generación contextual (FIX V2 §13, caso T07).
    """
    if not entity_ids:
        raise GeographyUnresolved(
            "la competición no tiene territorio resuelto",
            ["busca un lugar con /api/v1/geography/search y elige una entidad"],
        )
    entidades = []
    for identificador in entity_ids:
        fila = session.get(m.GazetteerEntity, identificador)
        if fila is None:
            raise GeographyUnresolved(
                f"«{identificador}» no es una entidad geográfica resuelta de este gazetteer",
                [
                    "un nombre escrito a mano no sirve como territorio: busca el "
                    "lugar y usa el identificador que devuelve la búsqueda"
                ],
            )
        entidades.append(fila)

    paises = _countries_by_iso(session, {f.country_iso2 for f in entidades})
    sin_moneda = sorted(
        {
            f.country_iso2
            for f in entidades
            if not (paises.get(f.country_iso2, None) and paises[f.country_iso2].currency_code)
        }
    )
    sin_coste = sorted(
        {
            f.country_iso2
            for f in entidades
            if paises.get(f.country_iso2) is not None
            and paises[f.country_iso2].reference_monthly_cost is None
        }
    )
    avisos: list[str] = []
    if sin_moneda:
        avisos.append(
            f"No se conoce la moneda de curso legal de {', '.join(sin_moneda)}: las "
            "cuentas de sus clubes quedarán sin cuantificar."
        )
    if sin_coste:
        avisos.append(
            f"No hay coste de referencia curado para {', '.join(sin_coste)}: los clubes "
            "de esa jurisdicción se generarán con las partidas declaradas pero **sin "
            "importes**, marcadas como datos insuficientes. Es deliberado: antes un "
            "hueco declarado que una cifra inventada."
        )
    return {
        "status": "verified",
        "entities": [_entity_brief(session, f, paises.get(f.country_iso2)) for f in entidades],
        "countries": sorted({f.country_iso2 for f in entidades}),
        "currencies": sorted({p.currency_code for p in paises.values() if p and p.currency_code}),
        "population": sum(f.population for f in entidades),
        "warnings": avisos,
    }


# --------------------------------------------------------------------------- #
# Ayudantes
# --------------------------------------------------------------------------- #


def _cos_lat(lat: float) -> float:
    import math

    return max(0.01, math.cos(math.radians(lat)))


def _countries_by_iso(session: Session, codes: set[str]) -> dict[str, m.GazetteerCountry]:
    if not codes:
        return {}
    return {
        row.iso2: row
        for row in session.scalars(
            select(m.GazetteerCountry).where(m.GazetteerCountry.iso2.in_(sorted(codes)))
        ).all()
    }


def _ancestors(session: Session, fila: m.GazetteerEntity) -> list[m.GazetteerEntity]:
    out: list[m.GazetteerEntity] = []
    visto: set[str] = {fila.id}
    actual = session.get(m.GazetteerEntity, fila.parent_id) if fila.parent_id else None
    while actual is not None and actual.id not in visto:
        visto.add(actual.id)
        out.append(actual)
        actual = session.get(m.GazetteerEntity, actual.parent_id) if actual.parent_id else None
    return out


def _entity_brief(
    session: Session, fila: m.GazetteerEntity, pais: m.GazetteerCountry | None
) -> dict[str, Any]:
    ancestros = _ancestors(session, fila)
    return {
        "id": fila.id,
        "name": fila.name,
        "kind": fila.kind,
        "country_iso2": fila.country_iso2,
        "country_name": pais.name if pais else fila.country_iso2,
        "admin_path": " · ".join(a.name for a in reversed(ancestros)) or None,
        "lat": fila.lat,
        "lon": fila.lon,
        "elevation_m": fila.elevation_m,
        "population": fila.population or None,
        "timezone": fila.timezone,
        "feature_code": fila.feature_code,
        "currency": pais.currency_code if pais else None,
        "source": fila.source,
        "source_id": fila.source_id,
        "status": fila.resolution_status,
        "status_notes": list(fila.resolution_notes),
    }


def _currency_info(pais: m.GazetteerCountry | None) -> dict[str, Any]:
    if pais is None or not pais.currency_code:
        return {
            "code": None,
            "name": None,
            "confidence": "missing",
            "reference_monthly_cost": None,
            "sources": [],
            "note": (
                "Sin moneda conocida para esta jurisdicción: las cuentas de sus "
                "instituciones no se pueden cuantificar."
            ),
        }
    return {
        "code": pais.currency_code,
        "name": pais.currency_name,
        "confidence": "observed",
        "reference_monthly_cost": (
            str(pais.reference_monthly_cost) if pais.reference_monthly_cost is not None else None
        ),
        "reference_cost_year": pais.reference_cost_year,
        "sources": [ATTRIBUTION, "ISO 4217", *list(pais.reference_cost_sources)],
        "note": (
            "Moneda de curso legal de la jurisdicción, con coste mensual de "
            "referencia curado: los importes de sus clubes se pueden calcular."
            if pais.reference_monthly_cost is not None
            else "Se conoce la moneda pero no el coste mensual de referencia: los "
            "clubes de esta jurisdicción se generan sin importes, marcados como "
            "datos insuficientes."
        ),
    }


def _boundary_info(session: Session, fila: m.GazetteerEntity) -> dict[str, Any]:
    limite = session.scalars(
        select(m.GazetteerBoundary).where(m.GazetteerBoundary.entity_id == fila.id)
    ).first()
    if limite is None:
        return {
            "available": False,
            "note": (
                "No hay límite administrativo publicado para esta entidad. El "
                "territorio se delimita por contención administrativa o por radio "
                "desde su centroide; no se dibuja ninguna frontera aproximada."
            ),
            "alternatives": ["administrative_containment", "radius"],
        }
    return {
        "available": True,
        "source": limite.source,
        "source_id": limite.source_id,
        "admin_level": limite.admin_level,
        "crs": limite.crs,
        "licence": limite.licence,
        "licence_source": limite.licence_source,
        "represented_year": limite.represented_year,
    }


def _curated_profile(session: Session, fila: m.GazetteerEntity):
    """Perfil curado del fixture, si este lugar es uno de los calibrados.

    Se busca por nombre y país: el fixture es anterior al gazetteer y no tiene
    `geonameid`. Si coincide, sus índices —que sí están calibrados a mano— tienen
    preferencia sobre el supuesto neutral.
    """
    objetivo = normalize(fila.name)
    for lugar in session.scalars(
        select(m.Place).where(m.Place.country_code == fila.country_iso2)
    ).all():
        if normalize(lugar.name) != objetivo:
            continue
        perfil = session.scalars(
            select(m.RegionProfile).where(m.RegionProfile.place_id == lugar.id)
        ).first()
        if perfil is not None:
            return perfil
    return None


def _context_warnings(
    fila: m.GazetteerEntity, pais: m.GazetteerCountry | None, curado: bool
) -> list[str]:
    avisos: list[str] = []
    if fila.resolution_status != "verified":
        avisos.extend(fila.resolution_notes)
    if not fila.population:
        avisos.append(
            "La fuente no publica población de esta entidad: no se puede estimar "
            "el tamaño de su mercado deportivo."
        )
    if pais is None or not pais.currency_code:
        avisos.append("Sin moneda conocida: las cuentas de sus clubes quedarán sin cifra.")
    elif pais.reference_monthly_cost is None:
        avisos.append(
            f"Se conoce la moneda ({pais.currency_code}) pero no el coste mensual de "
            "referencia de esta jurisdicción: los importes quedarán sin determinar."
        )
    if not curado:
        avisos.append(
            "No hay evidencia local de actividad beisbolística, economía ni "
            "infraestructura deportiva para este territorio: los índices son un "
            "supuesto neutral declarado y conviene calibrarlos."
        )
    return avisos
