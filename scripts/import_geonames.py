#!/usr/bin/env python3
"""Importa el gazetteer mundial de GeoNames a la base de datos.

Qué trae y de dónde:

| Fichero | Qué aporta | Tamaño |
|---|---|---|
| `countryInfo.txt` | ISO 3166-1, **moneda ISO 4217**, población, capital | 31 KB |
| `admin1CodesASCII.txt` | divisiones de primer nivel (estados, regiones) | 150 KB |
| `admin2Codes.txt` | divisiones de segundo nivel (provincias, municipios) | 2,4 MB |
| `cities500.txt` | **236.000 localidades** de 500 habitantes o más, con variantes de nombre | 42 MB |

Licencia: los datos de GeoNames están bajo **Creative Commons Attribution
4.0**, que exige atribución. La importación la guarda en cada fila
(`source`, `source_id`) y la interfaz la muestra. Ver `data/gazetteer/README.md`.

Uso:

    # 1) descargar los ficheros oficiales a un directorio propio
    python scripts/import_geonames.py --download --source-dir data/gazetteer/geonames

    # 2) importar (idempotente: reimportar actualiza, no duplica)
    python scripts/import_geonames.py --source-dir data/gazetteer/geonames

    # variantes útiles
    python scripts/import_geonames.py --source-dir DIR --only-countries MX,UG
    python scripts/import_geonames.py --source-dir DIR --min-population 5000

La descarga es un paso **explícito y aparte**: el simulador nunca sale a la red
por su cuenta, y una vez importado funciona sin conexión.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.request
import zipfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from app.infrastructure import models as m
from app.infrastructure.database import new_id, session_scope

from simulation.geography.geonames import (
    ATTRIBUTION,
    SOURCE,
    normalize,
    parse_admin_codes,
    parse_country_info,
    parse_geonames,
    search_text,
)

BASE_URL = "https://download.geonames.org/export/dump"
FILES = {
    "countryInfo.txt": "countryInfo.txt",
    "admin1CodesASCII.txt": "admin1CodesASCII.txt",
    "admin2Codes.txt": "admin2Codes.txt",
    "cities500.zip": "cities500.txt",
}

#: Anclas monetarias curadas: coste mensual de referencia de un hogar en moneda
#: local. Es el único dato que no viene de GeoNames, porque GeoNames no lo
#: publica. Un país que no esté aquí conserva su moneda pero **no** recibe
#: importes: sus clubes salen con las cuentas sin cuantificar.
CURATED_REFERENCE_COSTS: dict[str, tuple[Decimal, int]] = {
    "MX": (Decimal("12000"), 2025),
    "AR": (Decimal("700000"), 2025),
    "BR": (Decimal("3200"), 2025),
    "CU": (Decimal("15000"), 2025),
    "DO": (Decimal("35000"), 2025),
}
CURATED_SOURCES = [
    "orden de magnitud de gasto mensual de hogar, estimación propia",
    "moneda: ISO 4217 vía GeoNames countryInfo",
]

CHUNK = 2_000


def download(source_dir: Path) -> None:
    source_dir.mkdir(parents=True, exist_ok=True)
    for remote in FILES:
        destino = source_dir / remote
        print(f"descargando {remote}…", end=" ", flush=True)
        inicio = time.perf_counter()
        with urllib.request.urlopen(f"{BASE_URL}/{remote}", timeout=180) as respuesta:
            destino.write_bytes(respuesta.read())
        print(f"{destino.stat().st_size / 1e6:.1f} MB en {time.perf_counter() - inicio:.1f}s")
        if remote.endswith(".zip"):
            with zipfile.ZipFile(destino) as zf:
                zf.extract(FILES[remote], path=source_dir)
            print(f"  descomprimido {FILES[remote]}")
    (source_dir / "ATTRIBUTION.txt").write_text(
        f"{ATTRIBUTION}\nDescargado de {BASE_URL} el {time.strftime('%Y-%m-%d')}.\n",
        encoding="utf-8",
    )


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _resolve_path(source_dir: Path, remote: str) -> Path:
    """Devuelve el fichero de texto, descomprimiendo el zip si hace falta."""
    nombre = FILES[remote]
    directo = source_dir / nombre
    if directo.exists():
        return directo
    comprimido = source_dir / remote
    if comprimido.exists() and comprimido.suffix == ".zip":
        with zipfile.ZipFile(comprimido) as zf:
            zf.extract(nombre, path=source_dir)
        return directo
    raise SystemExit(
        f"falta {nombre} en {source_dir}. Ejecuta primero:\n"
        f"  python scripts/import_geonames.py --download --source-dir {source_dir}"
    )


def import_gazetteer(
    source_dir: Path,
    only_countries: set[str] | None = None,
    min_population: int = 0,
) -> dict[str, int]:
    paises = parse_country_info(_lines(_resolve_path(source_dir, "countryInfo.txt")))
    admin1 = parse_admin_codes(_lines(_resolve_path(source_dir, "admin1CodesASCII.txt")))
    admin2 = parse_admin_codes(_lines(_resolve_path(source_dir, "admin2Codes.txt")))
    localidades_path = _resolve_path(source_dir, "cities500.zip")

    if only_countries:
        paises = [c for c in paises if c.iso2 in only_countries]
        admin1 = [a for a in admin1 if a.country_iso2 in only_countries]
        admin2 = [a for a in admin2 if a.country_iso2 in only_countries]

    conteo = {"paises": 0, "admin": 0, "localidades": 0, "sin_moneda": 0, "saltadas": 0}
    admitidos = {c.iso2 for c in paises}

    with session_scope() as session:
        indice = _EntityIndex(session)

        # --- Países ------------------------------------------------------ #
        existentes = {row.iso2 for row in session.query(m.GazetteerCountry).all()}
        for pais in paises:
            curado = CURATED_REFERENCE_COSTS.get(pais.iso2)
            datos = {
                "iso2": pais.iso2,
                "iso3": pais.iso3,
                "name": pais.name,
                "capital": pais.capital,
                "continent": pais.continent,
                "currency_code": pais.currency_code or None,
                "currency_name": pais.currency_name or None,
                "population": pais.population,
                "area_km2": pais.area_km2,
                "geoname_id": pais.geoname_id,
                "languages": list(pais.languages),
                "reference_monthly_cost": curado[0] if curado else None,
                "reference_cost_year": curado[1] if curado else None,
                "reference_cost_sources": CURATED_SOURCES if curado else [],
                "source": SOURCE,
            }
            if pais.iso2 in existentes:
                session.query(m.GazetteerCountry).filter_by(iso2=pais.iso2).update(datos)
            else:
                session.add(m.GazetteerCountry(**datos))
            conteo["paises"] += 1
            if not pais.has_currency:
                conteo["sin_moneda"] += 1
        session.flush()

        # --- Divisiones administrativas ---------------------------------- #
        # Se insertan por nivel para que el padre exista antes que el hijo.
        por_codigo: dict[str, str] = {}
        iso_a_id: dict[str, str] = {}
        for pais in paises:
            iso_a_id[pais.iso2] = indice.upsert(
                session,
                new_id(),
                source_id=str(pais.geoname_id or f"iso:{pais.iso2}"),
                kind="country",
                name=pais.name,
                ascii_name=pais.name,
                variants=[pais.name],
                country_iso2=pais.iso2,
                parent_id=None,
                lat=0.0,
                lon=0.0,
                population=pais.population,
                feature_code="PCLI",
                timezone="UTC",
                admin1_code=None,
                admin2_code=None,
            )

        for nivel, registros in ((1, admin1), (2, admin2)):
            for admin in registros:
                padre = (
                    iso_a_id.get(admin.country_iso2)
                    if nivel == 1
                    else por_codigo.get(admin.parent_code or "")
                )
                if padre is None:
                    conteo["saltadas"] += 1
                    continue
                partes = admin.code.split(".")
                por_codigo[admin.code] = indice.upsert(
                    session,
                    new_id(),
                    source_id=str(admin.geoname_id),
                    kind="region",
                    name=admin.name,
                    ascii_name=admin.ascii_name,
                    variants=[admin.name, admin.ascii_name],
                    country_iso2=admin.country_iso2,
                    parent_id=padre,
                    lat=0.0,
                    lon=0.0,
                    population=0,
                    feature_code=f"ADM{nivel}",
                    timezone="UTC",
                    admin1_code=partes[1] if len(partes) > 1 else None,
                    admin2_code=partes[2] if len(partes) > 2 else None,
                    resolution_status="incomplete",
                    resolution_notes=[
                        "división administrativa sin centroide ni población propios en "
                        "la fuente: se usan los de sus localidades"
                    ],
                )
                conteo["admin"] += 1
            session.flush()

        # --- Localidades -------------------------------------------------- #
        lote: list[dict] = []
        for fila in parse_geonames(_lines(localidades_path)):
            if fila.kind is None:
                conteo["saltadas"] += 1
                continue
            if only_countries and fila.country_iso2 not in admitidos:
                continue
            if fila.population < min_population:
                continue
            padre = (
                por_codigo.get(fila.admin2_key or "")
                or por_codigo.get(fila.admin1_key or "")
                or iso_a_id.get(fila.country_iso2)
            )
            notas: list[str] = []
            estado = "verified"
            if padre is None:
                estado = "incomplete"
                notas.append("sin país conocido en el gazetteer")
            elif not fila.admin1_code:
                estado = "incomplete"
                notas.append("la fuente no indica su división administrativa de primer nivel")
            lote.append(
                {
                    "id": new_id(),
                    "source": SOURCE,
                    "source_id": str(fila.geoname_id),
                    "kind": str(fila.kind),
                    "name": fila.name,
                    "ascii_name": fila.ascii_name,
                    "search_text": normalize(search_text(fila)),
                    "variants": list(fila.alternate_names[:12]),
                    "country_iso2": fila.country_iso2,
                    "admin1_code": fila.admin1_code or None,
                    "admin2_code": fila.admin2_code or None,
                    "parent_id": padre,
                    "lat": fila.lat,
                    "lon": fila.lon,
                    "elevation_m": fila.effective_elevation_m,
                    "population": fila.population,
                    "feature_class": fila.feature_class,
                    "feature_code": fila.feature_code,
                    "timezone": fila.timezone or "UTC",
                    "resolution_status": estado,
                    "resolution_notes": notas,
                }
            )
            if len(lote) >= CHUNK:
                conteo["localidades"] += _flush_batch(session, indice, lote)
                lote.clear()
        if lote:
            conteo["localidades"] += _flush_batch(session, indice, lote)
    return conteo


class _EntityIndex:
    """Índice en memoria de lo ya importado, por `source_id`.

    Se carga de una vez al empezar. La alternativa —una consulta por fila— son
    51.000  idas y venidas a la base solo para las divisiones administrativas
    del mundo, y convierte una importación de segundos en una de minutos.
    """

    def __init__(self, session) -> None:
        self.por_source_id: dict[str, m.GazetteerEntity] = {
            fila.source_id: fila
            for fila in session.query(m.GazetteerEntity)
            .filter(m.GazetteerEntity.source == SOURCE)
            .all()
        }

    def upsert(self, session, identificador: str, **datos) -> str:
        """Inserta o actualiza, y devuelve el id definitivo de la entidad."""
        fila = self.por_source_id.get(datos["source_id"])
        if fila is not None:
            for clave, valor in datos.items():
                setattr(fila, clave, valor)
            return fila.id
        nueva = m.GazetteerEntity(id=identificador, source=SOURCE, **datos)
        session.add(nueva)
        self.por_source_id[datos["source_id"]] = nueva
        return identificador


def _flush_batch(session, indice: _EntityIndex, lote: list[dict]) -> int:
    """Inserta un lote, actualizando lo que ya estuviera por `source_id`."""
    nuevos = []
    for datos in lote:
        fila = indice.por_source_id.get(datos["source_id"])
        if fila is None:
            nuevos.append(datos)
            continue
        for clave, valor in datos.items():
            if clave != "id":
                setattr(fila, clave, valor)
    if nuevos:
        session.bulk_insert_mappings(m.GazetteerEntity, nuevos)
        # El índice recuerda que ya existen, para que un `source_id` repetido en
        # el mismo volcado no se inserte dos veces.
        for datos in nuevos:
            indice.por_source_id[datos["source_id"]] = None  # type: ignore[assignment]
    session.flush()
    return len(lote)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=ROOT / "data" / "gazetteer" / "geonames",
        help="directorio con los ficheros de GeoNames",
    )
    parser.add_argument(
        "--download", action="store_true", help="descarga los ficheros antes de importar"
    )
    parser.add_argument(
        "--only-countries", default="", help="lista ISO2 separada por comas, para importar menos"
    )
    parser.add_argument(
        "--min-population", type=int, default=0, help="descarta localidades más pequeñas"
    )
    args = parser.parse_args()

    if args.download:
        download(args.source_dir)

    solo = {c.strip().upper() for c in args.only_countries.split(",") if c.strip()}
    inicio = time.perf_counter()
    conteo = import_gazetteer(
        args.source_dir, only_countries=solo or None, min_population=args.min_population
    )
    segundos = time.perf_counter() - inicio

    print(
        f"\nimportado en {segundos:.1f}s: {conteo['paises']} países "
        f"({conteo['sin_moneda']} sin moneda declarada), {conteo['admin']} divisiones "
        f"administrativas y {conteo['localidades']} localidades. "
        f"{conteo['saltadas']} filas saltadas por no ser jurisdicciones o asentamientos."
    )
    print(f"atribución registrada: {ATTRIBUTION}")
    print(
        "Las monedas salen de ISO 4217 por jurisdicción. El coste mensual de "
        "referencia solo está curado para "
        f"{', '.join(sorted(CURATED_REFERENCE_COSTS))}: los demás países conservan su "
        "moneda pero sus clubes quedan sin importes, declarado como datos insuficientes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
