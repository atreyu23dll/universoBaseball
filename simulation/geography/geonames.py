"""Lectura del gazetteer de GeoNames: el mundo entero, sin lista cerrada.

Por qué existe este módulo: la Fase 1 original resolvía el territorio con un
fixture local de 25 entradas, y el FIX V2 (§4.1) lo prohíbe —«no usar una lista
local fija como fuente principal»—. Aquí se parsean los **ficheros descargables
oficiales** de GeoNames, que cubren 236 632 localidades de 500 habitantes o más
en todo el mundo, con sus divisiones administrativas y sus variantes de nombre.

Qué es y qué no es cada cosa:

- `GeoNames` aporta **identidad, jerarquía, coordenadas, población y moneda del
  país**. Son datos con fuente citable y `source_id` estable (`geonameid`).
- `GeoNames` **no** aporta economía local, cultura beisbolística ni
  infraestructura deportiva. Eso no se infiere del país ni se inventa: se marca
  como supuesto de escenario declarado o como dato ausente, y el motor avisa.

Licencia: los datos de GeoNames se publican bajo **CC BY 4.0** y exigen
atribución. Ver `data/gazetteer/README.md`. Este módulo solo parsea ficheros que
ya están en disco: no descarga nada ni habla con ningún servicio.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from simulation.core.provenance import Confidence
from simulation.geography.model import (
    EconomicAnchor,
    Place,
    PlaceKind,
    PlaceTree,
    RegionProfile,
)

SOURCE = "geonames"
#: Atribución obligatoria por la licencia de los datos.
ATTRIBUTION = "GeoNames (https://www.geonames.org), CC BY 4.0"

#: Códigos de entidad que interesan y a qué nivel del modelo corresponden.
#: GeoNames distingue decenas de tipos; aquí solo se admiten los que son
#: jurisdicciones o asentamientos, y el resto se ignora en vez de colarse como
#: si fuera una ciudad.
FEATURE_TO_KIND = {
    # Países y territorios dependientes.
    "PCLI": PlaceKind.COUNTRY,
    "PCLD": PlaceKind.COUNTRY,
    "PCLIX": PlaceKind.COUNTRY,
    "PCLS": PlaceKind.COUNTRY,
    "PCLF": PlaceKind.COUNTRY,
    "TERR": PlaceKind.COUNTRY,
    # Divisiones administrativas.
    "ADM1": PlaceKind.REGION,
    "ADM2": PlaceKind.REGION,
    "ADM3": PlaceKind.REGION,
    "ADM4": PlaceKind.REGION,
    # Asentamientos.
    "PPLC": PlaceKind.CITY,  # capital de país
    "PPLA": PlaceKind.CITY,  # capital de ADM1
    "PPLA2": PlaceKind.CITY,
    "PPLA3": PlaceKind.CITY,
    "PPLA4": PlaceKind.CITY,
    "PPLA5": PlaceKind.CITY,
    "PPL": PlaceKind.CITY,
    "PPLG": PlaceKind.CITY,
    "PPLS": PlaceKind.CITY,
    "PPLL": PlaceKind.CITY,
    "PPLR": PlaceKind.CITY,
    "PPLF": PlaceKind.CITY,
    # Barrios y secciones de ciudad: son distritos reales, no ciudades.
    "PPLX": PlaceKind.DISTRICT,
}


@dataclass(frozen=True)
class CountryRecord:
    """Una fila de `countryInfo.txt`.

    `currency_code` es la respuesta a «¿en qué moneda opera una institución de
    este territorio?», y viene de un dato territorial independiente —no del
    idioma de la interfaz ni de un ajuste del universo (FIX V2 §4.4)—.
    """

    iso2: str
    iso3: str
    name: str
    capital: str
    area_km2: float | None
    population: int
    continent: str
    currency_code: str
    currency_name: str
    languages: tuple[str, ...]
    geoname_id: int | None

    @property
    def has_currency(self) -> bool:
        return bool(self.currency_code)


@dataclass(frozen=True)
class AdminRecord:
    """Una división administrativa de `admin1CodesASCII.txt` o `admin2Codes.txt`."""

    code: str
    name: str
    ascii_name: str
    geoname_id: int

    @property
    def country_iso2(self) -> str:
        return self.code.split(".")[0]

    @property
    def parent_code(self) -> str | None:
        partes = self.code.split(".")
        return ".".join(partes[:-1]) if len(partes) > 2 else None

    @property
    def level(self) -> int:
        return len(self.code.split(".")) - 1


@dataclass(frozen=True)
class GeoNameRow:
    """Una fila del volcado principal (`cities500.txt`, `allCountries.txt`…).

    Se conserva `geoname_id` como **identificador externo estable**: es lo que
    permite volver a la fuente, reimportar sin duplicar y citar de dónde salió
    cada lugar.
    """

    geoname_id: int
    name: str
    ascii_name: str
    alternate_names: tuple[str, ...]
    lat: float
    lon: float
    feature_class: str
    feature_code: str
    country_iso2: str
    admin1_code: str
    admin2_code: str
    admin3_code: str
    admin4_code: str
    population: int
    elevation_m: int | None
    dem_m: int | None
    timezone: str
    modified_on: str

    @property
    def kind(self) -> PlaceKind | None:
        return FEATURE_TO_KIND.get(self.feature_code)

    @property
    def admin1_key(self) -> str | None:
        return f"{self.country_iso2}.{self.admin1_code}" if self.admin1_code else None

    @property
    def admin2_key(self) -> str | None:
        if not (self.admin1_code and self.admin2_code):
            return None
        return f"{self.country_iso2}.{self.admin1_code}.{self.admin2_code}"

    @property
    def effective_elevation_m(self) -> int:
        """Altitud declarada o, si falta, el modelo digital de elevación.

        La altitud afecta al vuelo de la pelota, así que conviene tenerla; el
        `dem` es menos preciso que una medición, y por eso se prefiere la
        primera cuando existe.
        """
        if self.elevation_m is not None:
            return self.elevation_m
        return self.dem_m or 0


def _int_or_none(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_country_info(lines: Iterable[str]) -> list[CountryRecord]:
    """Parsea `countryInfo.txt`. Las líneas que empiezan por `#` son comentario."""
    out: list[CountryRecord] = []
    for raw in lines:
        if not raw.strip() or raw.startswith("#"):
            continue
        campos = raw.rstrip("\n").split("\t")
        if len(campos) < 17:
            continue
        area = campos[6].strip()
        out.append(
            CountryRecord(
                iso2=campos[0].strip(),
                iso3=campos[1].strip(),
                name=campos[4].strip(),
                capital=campos[5].strip(),
                area_km2=float(area) if area else None,
                population=_int_or_none(campos[7]) or 0,
                continent=campos[8].strip(),
                currency_code=campos[10].strip(),
                currency_name=campos[11].strip(),
                languages=tuple(x for x in campos[15].split(",") if x),
                geoname_id=_int_or_none(campos[16]),
            )
        )
    return out


def parse_admin_codes(lines: Iterable[str]) -> list[AdminRecord]:
    """Parsea `admin1CodesASCII.txt` o `admin2Codes.txt`."""
    out: list[AdminRecord] = []
    for raw in lines:
        if not raw.strip():
            continue
        campos = raw.rstrip("\n").split("\t")
        if len(campos) < 4:
            continue
        identificador = _int_or_none(campos[3])
        if identificador is None:
            continue
        out.append(
            AdminRecord(
                code=campos[0].strip(),
                name=campos[1].strip(),
                ascii_name=campos[2].strip(),
                geoname_id=identificador,
            )
        )
    return out


def parse_geonames(lines: Iterable[str]) -> Iterator[GeoNameRow]:
    """Parsea el volcado principal. Generador: no carga 40 MB en memoria."""
    for raw in lines:
        if not raw.strip():
            continue
        campos = raw.rstrip("\n").split("\t")
        if len(campos) < 19:
            continue
        try:
            yield GeoNameRow(
                geoname_id=int(campos[0]),
                name=campos[1],
                ascii_name=campos[2],
                alternate_names=tuple(x for x in campos[3].split(",") if x),
                lat=float(campos[4]),
                lon=float(campos[5]),
                feature_class=campos[6],
                feature_code=campos[7],
                country_iso2=campos[8],
                admin1_code=campos[10],
                admin2_code=campos[11],
                admin3_code=campos[12],
                admin4_code=campos[13],
                population=_int_or_none(campos[14]) or 0,
                elevation_m=_int_or_none(campos[15]),
                dem_m=_int_or_none(campos[16]),
                timezone=campos[17],
                modified_on=campos[18],
            )
        except (ValueError, IndexError):
            # Una fila corrupta no puede tumbar una importación de 236.000: se
            # salta y el importador cuenta cuántas se saltaron.
            continue


def search_text(row: GeoNameRow) -> str:
    """Texto normalizado para buscar: nombre, ascii y variantes.

    Las variantes son lo que permite encontrar «Mexico City» escribiendo
    «Ciudad de México» y al revés, que es media usabilidad de un buscador
    geográfico.
    """
    partes = [row.name, row.ascii_name, *row.alternate_names]
    return " | ".join(dict.fromkeys(p for p in partes if p))


def normalize(text: str) -> str:
    """Minúsculas sin acentos, para comparar nombres de cualquier idioma."""
    import unicodedata

    descompuesto = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


# --------------------------------------------------------------------------- #
# Proveedor para el motor: un PlaceTree desde ficheros, sin base de datos
# --------------------------------------------------------------------------- #


@dataclass
class GeoNamesProvider:
    """Construye un `PlaceTree` desde ficheros de GeoNames en disco.

    Lo usa el motor cuando hay que simular un territorio cualquiera del mundo
    sin pasar por la base de datos (pruebas, scripts, cálculo de niveles). El
    backend tiene su propio camino, que lee el gazetteer ya importado.

    **Perfiles regionales:** GeoNames da población con fuente; no da economía,
    cultura deportiva ni infraestructura. Para esos índices este proveedor usa
    `scenario_assumption`: un supuesto neutral declarado, nunca un estereotipo
    por país. Si una jurisdicción tiene datos curados, se superponen aparte.
    """

    countries_path: Path
    geonames_path: Path
    admin1_path: Path | None = None
    admin2_path: Path | None = None
    #: Anclas monetarias curadas (coste mensual de referencia) por ISO2. Sin
    #: ancla, las instituciones de ese país salen sin importes.
    reference_costs: dict[str, Decimal] = field(default_factory=dict)
    reference_cost_year: int = 2025

    def load(self) -> PlaceTree:
        countries = {c.iso2: c for c in parse_country_info(_read(self.countries_path))}
        admin1 = (
            {a.code: a for a in parse_admin_codes(_read(self.admin1_path))}
            if self.admin1_path
            else {}
        )
        admin2 = (
            {a.code: a for a in parse_admin_codes(_read(self.admin2_path))}
            if self.admin2_path
            else {}
        )

        tree = PlaceTree()
        usados: set[str] = set()

        for iso2, country in countries.items():
            anchor = self._anchor_for(country)
            tree.places[iso2] = Place(
                key=iso2,
                kind=PlaceKind.COUNTRY,
                name=country.name,
                country_code=iso2,
                timezone="UTC",
                lat=0.0,
                lon=0.0,
                confidence=Confidence.OBSERVED,
                sources=(ATTRIBUTION, "ISO 3166-1", "ISO 4217"),
                profile=_country_profile(country),
                economy=anchor,
            )
            usados.add(iso2)

        for code, admin in sorted(admin1.items()):
            if admin.country_iso2 not in tree.places:
                continue
            tree.places[code] = Place(
                key=code,
                kind=PlaceKind.REGION,
                name=admin.name,
                country_code=admin.country_iso2,
                timezone="UTC",
                lat=0.0,
                lon=0.0,
                parent_key=admin.country_iso2,
                confidence=Confidence.OBSERVED,
                sources=(ATTRIBUTION,),
            )
            usados.add(code)

        for code, admin in sorted(admin2.items()):
            padre = admin.parent_code
            if padre not in tree.places:
                continue
            tree.places[code] = Place(
                key=code,
                kind=PlaceKind.REGION,
                name=admin.name,
                country_code=admin.country_iso2,
                timezone="UTC",
                lat=0.0,
                lon=0.0,
                parent_key=padre,
                confidence=Confidence.OBSERVED,
                sources=(ATTRIBUTION,),
            )
            usados.add(code)

        for row in parse_geonames(_read(self.geonames_path)):
            kind = row.kind
            if kind is None or kind is PlaceKind.COUNTRY:
                continue
            key = f"{SOURCE}:{row.geoname_id}"
            padre = self._parent_key(row, tree)
            tree.places[key] = Place(
                key=key,
                kind=kind,
                name=row.name,
                country_code=row.country_iso2,
                timezone=row.timezone or "UTC",
                lat=row.lat,
                lon=row.lon,
                parent_key=padre,
                elevation_m=row.effective_elevation_m,
                confidence=Confidence.OBSERVED,
                sources=(ATTRIBUTION, f"geonameid {row.geoname_id}"),
                profile=_settlement_profile(row),
            )
        return tree

    def _parent_key(self, row: GeoNameRow, tree: PlaceTree) -> str | None:
        for candidato in (row.admin2_key, row.admin1_key, row.country_iso2):
            if candidato and candidato in tree.places:
                return candidato
        return None

    def _anchor_for(self, country: CountryRecord) -> EconomicAnchor | None:
        """Ancla monetaria: la moneda siempre; el coste solo si está curado."""
        if not country.has_currency:
            return None
        coste = self.reference_costs.get(country.iso2)
        if coste is None:
            # Se conoce la moneda pero no el coste de referencia: sin coste no
            # hay importes defendibles, y el motor lo dirá en vez de inventarlos.
            return None
        return EconomicAnchor(
            currency=country.currency_code,
            reference_monthly_cost=coste,
            ref_year=self.reference_cost_year,
            confidence=Confidence.ESTIMATED,
            sources=(
                "ISO 4217 vía GeoNames countryInfo",
                "coste mensual de referencia: estimación propia curada",
            ),
        )


def _read(path: Path | None) -> Iterator[str]:
    if path is None:
        return iter(())
    return iter(path.read_text(encoding="utf-8").splitlines())


def _country_profile(country: CountryRecord) -> RegionProfile:
    """Perfil de un país: población con fuente, índices como supuesto.

    Los índices socioeconómicos y deportivos **no** se derivan del país: salen
    marcados como supuesto de escenario con valor neutral, para que la interfaz
    pueda decir «esto es un supuesto, no un dato» y el usuario los calibre.
    """
    return RegionProfile(
        ref_year=2025,
        population=country.population,
        economy_index=0.5,
        baseball_culture_index=0.5,
        cost_of_living_index=0.5,
        infrastructure_index=0.5,
        confidence=Confidence.SCENARIO_ASSUMPTION,
        sources=(
            ATTRIBUTION,
            "población: GeoNames countryInfo",
            "índices: supuesto neutral declarado, sin evidencia local",
        ),
    )


def _settlement_profile(row: GeoNameRow) -> RegionProfile | None:
    if row.population <= 0:
        return None
    return RegionProfile(
        ref_year=2025,
        population=row.population,
        economy_index=0.5,
        baseball_culture_index=0.5,
        cost_of_living_index=0.5,
        infrastructure_index=0.5,
        confidence=Confidence.SCENARIO_ASSUMPTION,
        sources=(
            ATTRIBUTION,
            f"población: GeoNames geonameid {row.geoname_id}",
            "índices: supuesto neutral declarado, sin evidencia local",
        ),
    )
