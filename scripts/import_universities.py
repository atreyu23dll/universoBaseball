#!/usr/bin/env python3
"""Importa el catálogo mundial de universidades desde el fichero versionado.

**No hace ninguna petición de red.** Lee `data/universities/universities.ndjson.gz`,
que viaja con el repositorio y se regenera a mano con
`scripts/build_university_catalog.py`. Antes esto descargaba el volcado
completo de GeoNames —422 MB comprimidos, 1,8 GB en disco— para sacar mil
quinientas universidades mal repartidas por el mundo; ahora el fichero ocupa
unos pocos megas y trae un orden de magnitud más instituciones.

Cada institución llega con coordenadas propias. El territorio —provincia,
municipio, zona horaria— **no** se cree lo que diga la fuente: se resuelve
contra el gazetteer buscando la localidad real más cercana. Así una liga
municipal encuentra a sus universidades aunque la fuente no declare división
administrativa, que es lo que antes dejaba ciudades enteras sin ninguna.

Uso::

    python scripts/import_universities.py
    python scripts/import_universities.py --only-countries MX,US
    python scripts/import_universities.py --ensure        # no hace nada si ya está
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from math import floor
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from app.infrastructure import models as m
from app.infrastructure.database import new_id, session_scope

from simulation.geography.distance import haversine_km
from simulation.geography.geonames import normalize

CATALOG = ROOT / "data" / "universities" / "universities.ndjson.gz"
SOURCE = "wikidata"
LICENCE = "CC0 1.0"
#: Hasta dónde se busca la localidad que sitúa a una institución. Más allá no
#: se adivina: se guarda sin división administrativa y la búsqueda por radio
#: sigue encontrándola por sus coordenadas.
ANCHOR_RADIUS_KM = 60.0


def leer_catalogo(path: Path, only_countries: set[str] | None) -> Iterator[dict[str, Any]]:
    """Recorre el catálogo versionado sin cargarlo entero en memoria."""
    if not path.exists():
        raise SystemExit(
            f"falta el catálogo {path}. Se genera con "
            "`python scripts/build_university_catalog.py` y se versiona en el repositorio."
        )
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for linea in stream:
            linea = linea.strip()
            if not linea:
                continue
            fila = json.loads(linea)
            if only_countries and fila.get("country") not in only_countries:
                continue
            yield fila


@dataclass(frozen=True, slots=True)
class Localidad:
    """Lo justo de una localidad del gazetteer para situar un campus."""

    name: str
    lat: float
    lon: float
    admin1_code: str | None
    admin2_code: str | None
    timezone: str


def _localidades_por_pais(session, iso2: str) -> dict[tuple[int, int], list[Localidad]]:
    """Localidades de un país, repartidas en una rejilla de un grado.

    Estados Unidos tiene más de cien mil localidades y el catálogo miles de
    instituciones: compararlas todas contra todas serían cientos de millones
    de distancias. Con la rejilla, cada campus solo mira su celda y las ocho
    de alrededor, que a sesenta kilómetros es todo lo que puede alcanzar.
    """
    rejilla: dict[tuple[int, int], list[Localidad]] = {}
    filas = session.execute(
        select(
            m.GazetteerEntity.name,
            m.GazetteerEntity.lat,
            m.GazetteerEntity.lon,
            m.GazetteerEntity.admin1_code,
            m.GazetteerEntity.admin2_code,
            m.GazetteerEntity.timezone,
        ).where(
            m.GazetteerEntity.country_iso2 == iso2,
            m.GazetteerEntity.kind.in_(["city", "district"]),
        )
    )
    for nombre, lat, lon, admin1, admin2, huso in filas:
        celda = (floor(lat), floor(lon))
        rejilla.setdefault(celda, []).append(
            Localidad(nombre, lat, lon, admin1, admin2, huso or "UTC")
        )
    return rejilla


def _ancla(
    rejilla: dict[tuple[int, int], list[Localidad]], lat: float, lon: float
) -> Localidad | None:
    """La localidad real más cercana a un campus, si está lo bastante cerca."""
    mejor: Localidad | None = None
    mejor_distancia = ANCHOR_RADIUS_KM
    base_lat, base_lon = floor(lat), floor(lon)
    for delta_lat in (-1, 0, 1):
        for delta_lon in (-1, 0, 1):
            # La longitud da la vuelta al mundo: junto al antimeridiano, la
            # celda contigua a 179 es la -180, no la 180.
            celda = (base_lat + delta_lat, ((base_lon + delta_lon + 180) % 360) - 180)
            for localidad in rejilla.get(celda, ()):
                distancia = haversine_km(lat, lon, localidad.lat, localidad.lon)
                if distancia <= mejor_distancia:
                    mejor, mejor_distancia = localidad, distancia
    return mejor


def importar(path: Path, only_countries: set[str] | None = None) -> dict[str, int]:
    """Deja el catálogo local igual al fichero: añade, actualiza y retira.

    El fichero es la única verdad. Lo que ya no está en él se borra, incluido
    el catálogo viejo de GeoNames: si conviviesen las dos fuentes, la misma
    universidad entraría dos veces en una liga, con dos equipos y dos nombres
    distintos del mismo sitio.
    """
    cuentas = {
        "leidas": 0,
        "nuevas": 0,
        "actualizadas": 0,
        "sin_territorio": 0,
        "retiradas": 0,
    }
    print(f"importando universidades desde {path}…", flush=True)
    with session_scope() as session:
        existentes = {
            fila.source_id: fila
            for fila in session.scalars(
                select(m.EducationalInstitution).where(m.EducationalInstitution.source == SOURCE)
            )
        }
        cache_localidades: dict[str, dict[tuple[int, int], list[Localidad]]] = {}
        vistos: set[str] = set()
        for fila in leer_catalogo(path, only_countries):
            cuentas["leidas"] += 1
            iso2 = str(fila["country"]).upper()
            if iso2 not in cache_localidades:
                cache_localidades[iso2] = _localidades_por_pais(session, iso2)
            ancla = _ancla(cache_localidades[iso2], float(fila["lat"]), float(fila["lon"]))
            if ancla is None:
                cuentas["sin_territorio"] += 1
            valores = {
                "source": SOURCE,
                "source_id": str(fila["qid"]),
                "name": str(fila["name"])[:220],
                "ascii_name": normalize(str(fila["name"]))[:220],
                "country_iso2": iso2,
                # La división administrativa sale de la localidad resuelta, no
                # de la fuente: es la que usa el propio gazetteer para decir
                # qué hay dentro de un territorio.
                "admin1_code": ancla.admin1_code if ancla else None,
                "admin2_code": ancla.admin2_code if ancla else None,
                "lat": float(fila["lat"]),
                "lon": float(fila["lon"]),
                "timezone": (ancla.timezone if ancla and ancla.timezone else "UTC"),
                "source_url": f"https://www.wikidata.org/wiki/{fila['qid']}",
                "licence": LICENCE,
                "institution_type": (str(fila["type"])[:80] if fila.get("type") else None),
                "founded_year": int(fila["founded"]) if fila.get("founded") else None,
                "website": (str(fila["site"])[:300] if fila.get("site") else None),
                "locality_name": ancla.name if ancla else None,
            }
            if valores["source_id"] in vistos:
                # El fichero no debería traer repetidos, pero si los trae no se
                # cae a mitad de la importación: la identidad es el QID.
                continue
            vistos.add(valores["source_id"])
            previa = existentes.get(valores["source_id"])
            if previa is None:
                session.add(m.EducationalInstitution(id=new_id(), **valores))
                cuentas["nuevas"] += 1
            else:
                for campo, valor in valores.items():
                    setattr(previa, campo, valor)
                cuentas["actualizadas"] += 1

        cuentas["retiradas"] = _retirar_lo_que_ya_no_esta(session, vistos, only_countries)
    return cuentas


def _retirar_lo_que_ya_no_esta(session, vistos: set[str], only_countries: set[str] | None) -> int:
    """Borra el catálogo viejo y lo que la fuente ya no publica.

    Con un filtro de países solo se toca lo de esos países: importar México no
    puede vaciar el resto del mundo.
    """
    condiciones = []
    if only_countries:
        condiciones.append(m.EducationalInstitution.country_iso2.in_(sorted(only_countries)))
    sobrantes = [
        fila
        for fila in session.scalars(select(m.EducationalInstitution).where(*condiciones))
        if fila.source != SOURCE or fila.source_id not in vistos
    ]
    for fila in sobrantes:
        session.delete(fila)
    return len(sobrantes)


def total_en_base() -> int:
    with session_scope() as session:
        return session.scalar(select(func.count()).select_from(m.EducationalInstitution)) or 0


def hace_falta_resituar() -> bool:
    """¿El catálogo se importó antes que el gazetteer?

    En un arranque en limpio el gazetteer todavía está vacío, así que las
    instituciones entran sin provincia ni municipio. Cuando después se importa
    el mundo con `make import-geonames`, esas fichas seguirían sin territorio
    para siempre si nadie las volviera a situar. Esto lo detecta: hay
    localidades, pero casi ninguna institución está situada.
    """
    with session_scope() as session:
        # Solo se mira donde el gazetteer puede situar algo: con el extracto de
        # muestra, que trae nueve países, no tiene sentido esperar que esté
        # situada una universidad de Japón.
        cubiertos = (
            select(m.GazetteerEntity.country_iso2)
            .where(m.GazetteerEntity.kind.in_(["city", "district"]))
            .distinct()
            .scalar_subquery()
        )
        total = (
            session.scalar(
                select(func.count())
                .select_from(m.EducationalInstitution)
                .where(m.EducationalInstitution.country_iso2.in_(cubiertos))
            )
            or 0
        )
        if not total:
            return False
        situadas = session.scalar(
            select(func.count())
            .select_from(m.EducationalInstitution)
            .where(
                m.EducationalInstitution.country_iso2.in_(cubiertos),
                m.EducationalInstitution.locality_name.is_not(None),
            )
        )
        # Siempre hay unas pocas que ninguna localidad alcanza —islas, desierto—,
        # así que solo salta si falta la mayoría.
        return (situadas or 0) * 2 < total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument(
        "--ensure", action="store_true", help="no hace nada si la base ya tiene catálogo"
    )
    parser.add_argument("--only-countries", default="", help="ISO2 separados por coma")
    args = parser.parse_args()

    if args.ensure and (existentes := total_en_base()):
        if not hace_falta_resituar():
            print(f"catálogo universitario ya disponible: {existentes} instituciones", flush=True)
            return
        print(
            "el catálogo está sin situar y ya hay gazetteer: se vuelve a importar "
            "para darle a cada institución su provincia y su municipio",
            flush=True,
        )

    paises = {item.strip().upper() for item in args.only_countries.split(",") if item.strip()}
    cuentas = importar(args.catalog, paises or None)
    print(
        f"instituciones leídas: {cuentas['leidas']} "
        f"(nuevas: {cuentas['nuevas']}, actualizadas: {cuentas['actualizadas']}, "
        f"retiradas: {cuentas['retiradas']}, "
        f"sin localidad cercana en el gazetteer: {cuentas['sin_territorio']})"
    )


if __name__ == "__main__":  # pragma: no cover - punto de entrada
    main()
