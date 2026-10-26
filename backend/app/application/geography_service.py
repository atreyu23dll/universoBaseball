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

#: Cuántos puntos se siembran como máximo en una capa del globo. Por encima de
#: esto el globo deja de ser legible y el navegador deja de ir fluido; lo que
#: no entra se alcanza por búsqueda, no se oculta en silencio.
MAX_GLOBE_POINTS = 180


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
    admin_level: int | None = None,
    region_id: str | None = None,
    min_population: int = 0,
) -> dict[str, Any]:
    """Busca un lugar por nombre o variante y devuelve candidatos desambiguados.

    ``admin_level=1`` limita las regiones a estados/provincias. ``region_id``
    limita una búsqueda de localidades a la división de primer nivel elegida,
    para que el selector municipal no mezcle ciudades de otros estados.
    """
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

    # Las primeras importaciones guardaron ``search_text`` para localidades,
    # pero algunas filas administrativas antiguas quedaron sin ese índice.
    # ``ascii_name`` es parte de la fuente y mantiene países/provincias
    # buscables sin exigir reimportar todo el gazetteer.
    ascii_name = func.lower(m.GazetteerEntity.ascii_name)
    condiciones = [
        or_(
            m.GazetteerEntity.search_text.like(f"{texto}%"),
            m.GazetteerEntity.search_text.like(f"%|{texto}%"),
            m.GazetteerEntity.search_text.like(f"% {texto}%"),
            ascii_name.like(f"{texto}%"),
            ascii_name.like(f"% {texto}%"),
        )
    ]
    if country:
        condiciones.append(m.GazetteerEntity.country_iso2 == country.strip().upper())
    if kind:
        condiciones.append(m.GazetteerEntity.kind == kind.strip().lower())
    if admin_level is not None:
        if admin_level not in {1, 2}:
            raise GeographyUnresolved(
                "el nivel administrativo debe ser 1 (estado/provincia) o 2",
            )
        condiciones.append(m.GazetteerEntity.feature_code == f"ADM{admin_level}")
    if region_id:
        region = get_entity(session, region_id)
        if region.kind != "region" or region.feature_code != "ADM1" or not region.admin1_code:
            raise GeographyUnresolved(
                "la región elegida no es un estado o provincia de primer nivel",
            )
        if country and country.strip().upper() != region.country_iso2:
            raise GeographyUnresolved(
                "la región elegida no pertenece al país indicado",
            )
        condiciones.extend(
            [
                m.GazetteerEntity.country_iso2 == region.country_iso2,
                m.GazetteerEntity.admin1_code == region.admin1_code,
            ]
        )
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
    #
    # Antes de eso va un desempate menos obvio. Desde que países y divisiones
    # administrativas son buscables, una consulta como «juarez» compite entre
    # una ciudad de millón y medio de habitantes y una veintena de municipios
    # ADM2 llamados «Juárez» que el volcado trae sin población. Esos municipios
    # son contenedores: coinciden mejor por texto, pero sin cifra no hay con
    # qué ordenarlos entre sí ni forma de decir que uno es más relevante. Un
    # lugar con población tiene una respuesta mejor que ofrecer, así que va
    # delante; para llegar a una división está el filtro por tipo y nivel, que
    # es lo que usa el navegador territorial en su paso de provincia.
    def rango(fila: m.GazetteerEntity) -> tuple:
        nombre = normalize(fila.name)
        exacto = 0 if nombre == texto else (1 if nombre.startswith(texto) else 2)
        sin_poblacion = 0 if fila.population else 1
        return (
            sin_poblacion,
            exacto,
            KIND_RANK.get(fila.kind, 9),
            -fila.population,
            fila.name,
        )

    ordenadas = sorted(filas, key=rango)[: min(max(1, limit), MAX_RESULTS)]
    cache = _ancestor_cache(session, ordenadas)
    paises = _countries_by_iso(session, {f.country_iso2 for f in ordenadas})

    return {
        "query": query,
        "normalized": texto,
        "status": "candidates" if ordenadas else "unresolved",
        "total": len(ordenadas),
        "items": [
            _entity_brief(session, fila, paises.get(fila.country_iso2), cache) for fila in ordenadas
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


def aggregated_population(session: Session, entidad: m.GazetteerEntity) -> tuple[int, int]:
    """Población de una división administrativa, a partir de sus localidades.

    GeoNames no publica población para las divisiones administrativas: el
    importador las guarda con `population=0` y deja dicho en sus notas que «se
    usan los de sus localidades». Esta función es ese paso que faltaba.

    Importa porque sin ella una región entraba al universo **sin perfil**, y un
    lugar sin perfil heredaba el de su ancestro: cada estado mexicano acababa
    simulado con los 131,9 millones de habitantes de México.

    No es una suma simple, porque sumarlo todo cuenta a la misma gente dos
    veces. La fuente trae tres clases de registro mezcladas:

    - localidades situadas en un municipio, que no se solapan entre sí;
    - secciones de una localidad —colonias, delegaciones marcadas `PPLX`, que el
      importador guarda como `district`—, que ya están dentro de la anterior;
    - y a veces la capital contada entera y colgada del estado sin municipio,
      como «Mexico City» con 12,3 millones.

    Sumarlo todo daba 21,9 millones para la Ciudad de México. La regla es el
    mayor de dos cálculos: la suma de las **localidades con municipio**,
    excluidas las secciones; y la **mayor entrada sin municipio**, que suele ser
    justamente esa capital entera.

    Es una heurística declarada y parcial —solo cuenta lo que se importó, según
    el `--min-population` que se usara, y tiende a quedarse corta— y así se
    escribe en las fuentes del perfil que la usa.

    Devuelve `(población, localidades contadas)`; `(0, 0)` si no hay ninguna.
    """
    if entidad.kind != "region" or not entidad.admin1_code:
        return 0, 0
    condiciones = [
        m.GazetteerEntity.country_iso2 == entidad.country_iso2,
        m.GazetteerEntity.admin1_code == entidad.admin1_code,
        m.GazetteerEntity.population > 0,
    ]
    if entidad.feature_code == "ADM2" and entidad.admin2_code:
        condiciones.append(m.GazetteerEntity.admin2_code == entidad.admin2_code)

    con_municipio = session.execute(
        select(func.coalesce(func.sum(m.GazetteerEntity.population), 0), func.count()).where(
            *condiciones,
            m.GazetteerEntity.kind == "city",
            m.GazetteerEntity.admin2_code.is_not(None),
        )
    ).one()
    sin_municipio = session.execute(
        select(func.coalesce(func.max(m.GazetteerEntity.population), 0), func.count()).where(
            *condiciones,
            m.GazetteerEntity.kind.in_(["city", "district"]),
            m.GazetteerEntity.admin2_code.is_(None),
        )
    ).one()

    poblacion = max(int(con_municipio[0]), int(sin_municipio[0]))
    contadas = int(con_municipio[1]) + int(sin_municipio[1])
    return poblacion, contadas


def country_by_iso(session: Session, country_iso2: str) -> dict[str, Any]:
    """Devuelve un país por su ISO 3166-1 alpha-2, sin búsqueda textual.

    El globo selecciona polígonos cuya identidad estable es el código ISO. Esta
    ruta evita convertir un clic territorial en una búsqueda por nombre que
    podría ser ambigua o depender del idioma de la interfaz.
    """
    iso2 = country_iso2.strip().upper()
    fila = session.scalars(
        select(m.GazetteerEntity).where(
            m.GazetteerEntity.kind == "country",
            m.GazetteerEntity.country_iso2 == iso2,
        )
    ).first()
    if fila is None:
        raise NotFoundError(f"no existe un país del gazetteer con ISO {iso2}")
    pais = session.get(m.GazetteerCountry, iso2)
    return _entity_brief(session, fila, pais)


def regions_by_country(session: Session, country_iso2: str) -> list[dict[str, Any]]:
    """Puntos de las divisiones ADM1 de un país para la capa del globo.

    Son entidades de GeoNames, no contornos aproximados. Cuando no existe un
    polígono de una provincia, su marcador representativo sigue siendo
    seleccionable sin fingir que conocemos su frontera.
    """
    iso2 = country_iso2.strip().upper()
    pais = session.get(m.GazetteerCountry, iso2)
    if pais is None:
        raise NotFoundError(f"no existe un país del gazetteer con ISO {iso2}")
    filas = session.scalars(
        select(m.GazetteerEntity)
        .where(
            m.GazetteerEntity.country_iso2 == iso2,
            m.GazetteerEntity.kind == "region",
            m.GazetteerEntity.feature_code == "ADM1",
        )
        .order_by(m.GazetteerEntity.name)
    ).all()
    lote = list(filas)
    cache = _ancestor_cache(session, lote)
    anchors = _admin1_anchors(session, iso2, lote)
    return [_entity_brief(session, fila, pais, cache, anchors) for fila in lote]


def localities_by_region(
    session: Session, region_id: str, limit: int = MAX_GLOBE_POINTS
) -> dict[str, Any]:
    """Localidades de una división ADM1, para el último nivel del globo.

    Una provincia puede tener miles de localidades y el globo no puede
    mostrarlas todas: se devuelven las más pobladas y se dice cuántas quedaron
    fuera, en vez de insinuar que la lista es completa. Para una localidad
    pequeña está la búsqueda por nombre, que no tiene este tope.
    """
    region = get_entity(session, region_id)
    if region.kind != "region" or region.feature_code != "ADM1" or not region.admin1_code:
        raise GeographyUnresolved(
            "solo un estado o provincia de primer nivel contiene localidades "
            "seleccionables en el globo",
        )
    tope = min(max(1, limit), MAX_GLOBE_POINTS)
    condiciones = (
        m.GazetteerEntity.country_iso2 == region.country_iso2,
        m.GazetteerEntity.admin1_code == region.admin1_code,
        m.GazetteerEntity.kind.in_(["city", "district"]),
    )
    total = (
        session.scalar(select(func.count()).select_from(m.GazetteerEntity).where(*condiciones)) or 0
    )
    filas = session.scalars(
        select(m.GazetteerEntity)
        .where(*condiciones)
        .order_by(m.GazetteerEntity.population.desc(), m.GazetteerEntity.name)
        .limit(tope)
    ).all()
    cache = _ancestor_cache(session, list(filas))
    pais = session.get(m.GazetteerCountry, region.country_iso2)
    return {
        "region_id": region.id,
        "region_name": region.name,
        "country_iso2": region.country_iso2,
        "total": total,
        "shown": len(filas),
        "items": [_entity_brief(session, fila, pais, cache) for fila in filas],
        "attribution": ATTRIBUTION,
        "note": (
            f"{region.name} no tiene localidades en el gazetteer importado."
            if not filas
            else (
                f"Se muestran las {len(filas)} localidades más pobladas de "
                f"{total}. Busca por nombre si la que quieres no está en el globo."
                if total > len(filas)
                else f"Las {len(filas)} localidades de {region.name} que hay en el gazetteer."
            )
        ),
    }


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


def _ancestor_cache(
    session: Session, filas: list[m.GazetteerEntity]
) -> dict[str, m.GazetteerEntity]:
    """Jerarquía de un lote entero, por niveles y en pocas consultas.

    ``_ancestors`` sube por ``parent_id`` fila a fila, y con las 180 localidades
    de una capa del globo eso eran más de trescientas consultas —un segundo
    largo— para reconstruir el mismo puñado de municipios, provincias y países.
    No basta con dejarlos cargados en la sesión: su mapa de identidad guarda
    referencias débiles y los suelta en cuanto nadie los sostiene. Este
    diccionario es quien los sostiene mientras se arma la respuesta.
    """
    cache: dict[str, m.GazetteerEntity] = {}
    pendientes = {fila.parent_id for fila in filas if fila.parent_id}
    while pendientes:
        lote = {clave for clave in pendientes if clave not in cache}
        if not lote:
            break
        cargadas = session.scalars(
            select(m.GazetteerEntity).where(m.GazetteerEntity.id.in_(lote))
        ).all()
        for fila in cargadas:
            cache[fila.id] = fila
        pendientes = {fila.parent_id for fila in cargadas if fila.parent_id}
    return cache


def _ancestors(
    session: Session,
    fila: m.GazetteerEntity,
    cache: dict[str, m.GazetteerEntity] | None = None,
) -> list[m.GazetteerEntity]:
    def padre(entity_id: str) -> m.GazetteerEntity | None:
        if cache is not None and entity_id in cache:
            return cache[entity_id]
        return session.get(m.GazetteerEntity, entity_id)

    out: list[m.GazetteerEntity] = []
    visto: set[str] = {fila.id}
    actual = padre(fila.parent_id) if fila.parent_id else None
    while actual is not None and actual.id not in visto:
        visto.add(actual.id)
        out.append(actual)
        actual = padre(actual.parent_id) if actual.parent_id else None
    return out


def _entity_brief(
    session: Session,
    fila: m.GazetteerEntity,
    pais: m.GazetteerCountry | None,
    cache: dict[str, m.GazetteerEntity] | None = None,
    anchors: dict[str, tuple[float, float, str]] | None = None,
) -> dict[str, Any]:
    """Ficha breve de una entidad. ``cache`` y ``anchors`` son lo mismo que
    calcularía por su cuenta, pero resuelto en bloque para todo un lote."""
    ancestros = _ancestors(session, fila, cache)
    map_lat, map_lon, map_anchor = (
        anchors[fila.id] if anchors and fila.id in anchors else _map_coordinates(session, fila)
    )
    return {
        "id": fila.id,
        "name": fila.name,
        "kind": fila.kind,
        "country_iso2": fila.country_iso2,
        "country_name": pais.name if pais else fila.country_iso2,
        "admin_path": " · ".join(a.name for a in reversed(ancestros)) or None,
        "lat": fila.lat,
        "lon": fila.lon,
        # Países y divisiones administrativas del volcado no siempre traen
        # centroide. Para el globo usamos una localidad real representativa y
        # conservamos arriba las coordenadas originales, sin disfrazarlas.
        "map_lat": map_lat,
        "map_lon": map_lon,
        "map_anchor": map_anchor,
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


def _admin1_anchors(
    session: Session, country_iso2: str, filas: list[m.GazetteerEntity]
) -> dict[str, tuple[float, float, str]]:
    """Localidad representativa de cada provincia de un país, de una vez.

    Las divisiones administrativas del volcado no traen centroide, así que cada
    una se dibuja sobre su localidad más poblada. Resolverlas una por una era
    una consulta ordenada por población —sobre todas las ciudades del país—
    por provincia: cincuenta y una para Estados Unidos. Aquí se saca la primera
    de cada partición en una sola consulta.
    """
    objetivo = {
        fila.admin1_code: fila
        for fila in filas
        if fila.feature_code == "ADM1" and fila.admin1_code and fila.lat == 0.0 and fila.lon == 0.0
    }
    if not objetivo:
        return {}
    orden = func.row_number().over(
        partition_by=m.GazetteerEntity.admin1_code,
        order_by=(m.GazetteerEntity.population.desc(), m.GazetteerEntity.name),
    )
    candidatas = (
        select(
            m.GazetteerEntity.admin1_code.label("admin1_code"),
            m.GazetteerEntity.name.label("name"),
            m.GazetteerEntity.lat.label("lat"),
            m.GazetteerEntity.lon.label("lon"),
            orden.label("posicion"),
        )
        .where(
            m.GazetteerEntity.country_iso2 == country_iso2,
            m.GazetteerEntity.kind.in_(["city", "district"]),
            m.GazetteerEntity.admin1_code.in_(objetivo),
        )
        .subquery()
    )
    anclas: dict[str, tuple[float, float, str]] = {}
    for admin1_code, nombre, lat, lon in session.execute(
        select(
            candidatas.c.admin1_code, candidatas.c.name, candidatas.c.lat, candidatas.c.lon
        ).where(candidatas.c.posicion == 1)
    ):
        fila = objetivo.get(admin1_code)
        if fila is not None:
            anclas[fila.id] = (lat, lon, f"representative_locality:{nombre}")
    # Una provincia sin ninguna localidad en el gazetteer se queda sin ancla, y
    # `_map_coordinates` dirá que no la hay en vez de inventarle un punto.
    return anclas


def _map_coordinates(session: Session, fila: m.GazetteerEntity) -> tuple[float, float, str]:
    """Punto honesto para representar una entidad en el globo interactivo."""
    if fila.kind in {"city", "district"} or fila.lat != 0.0 or fila.lon != 0.0:
        return fila.lat, fila.lon, "entity"

    conditions = [
        m.GazetteerEntity.country_iso2 == fila.country_iso2,
        m.GazetteerEntity.kind.in_(["city", "district"]),
    ]
    if fila.feature_code == "ADM1" and fila.admin1_code:
        conditions.append(m.GazetteerEntity.admin1_code == fila.admin1_code)
    elif fila.feature_code == "ADM2" and fila.admin1_code and fila.admin2_code:
        conditions.extend(
            [
                m.GazetteerEntity.admin1_code == fila.admin1_code,
                m.GazetteerEntity.admin2_code == fila.admin2_code,
            ]
        )

    anchor = session.scalars(
        select(m.GazetteerEntity)
        .where(*conditions)
        .order_by(m.GazetteerEntity.population.desc(), m.GazetteerEntity.name)
        .limit(1)
    ).first()
    if anchor is None:
        return fila.lat, fila.lon, "unavailable"
    return anchor.lat, anchor.lon, f"representative_locality:{anchor.name}"


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
