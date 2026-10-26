#!/usr/bin/env python3
"""Construye el catálogo mundial de instituciones de educación superior.

Este script **no** forma parte del arranque ni de la API: se ejecuta a mano
cuando se quiere crear o refrescar el catálogo, y su resultado —un fichero
comprimido versionado en `data/universities/`— es lo único que lee el
importador. Ni el servidor ni el simulador consultan la red.

La fuente es Wikidata, que publica cada institución con coordenadas propias,
licencia **CC0 1.0** y un identificador estable (su QID). Se piden todas las
subclases de «institución de educación superior» (Q38723), que es lo que
incluye tecnológicos, escuelas normales, politécnicos y conservatorios, no solo
las universidades en sentido estricto.

Se consulta **país por país**: la consulta global agota el tiempo del servicio
público, y por países tarda un segundo cada una y permite reintentar solo lo
que falle.

Uso::

    python scripts/build_university_catalog.py
    python scripts/build_university_catalog.py --only-countries MX,US,JP
    python scripts/build_university_catalog.py --out data/universities/universities.ndjson.gz
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "BaseballUniverse/0.1 (catálogo territorial de universidades; contacto: repo local)"
#: Raíz del árbol educativo de Wikidata, que es por donde se pregunta.
ROOT_CLASS = "Q38723"

#: Qué cuenta como institución de educación superior, por clase de Wikidata.
#:
#: El árbol de «institución educativa universitaria» (Q38723) no sirve tal
#: cual: cuelgan de él casi diez mil escuelas primarias y secundarias mal
#: clasificadas —sobre todo de la India y Pakistán— junto a academias
#: científicas, que son sociedades de sabios y no dan clase. Por eso la lista
#: es explícita: se piden estas clases y todas sus subclases, y lo que no esté
#: aquí no entra. Se prefiere que falte una institución rara a que el catálogo
#: meta en una liga a una escuela primaria.
#:
#: Ojo: la raíz del árbol **no** puede estar aquí. Admitir Q38723 con sus
#: subclases es admitirlo todo, que es justo lo que había que evitar; para las
#: que solo declaran esa clase genérica está `ALLOWED_EXACT`.
ALLOWED_CLASSES = {
    "Q3918": "universidad",
    "Q189004": "college",
    "Q2680291": "colegio mayor",
    "Q1365560": "universidad de ciencias aplicadas",
    "Q1663017": "escuela de ingeniería",
    "Q1143635": "escuela de negocios",
    "Q494230": "escuela de medicina",
    "Q17072837": "medical college (India)",
    "Q446901": "escuela de enfermería",
    "Q845392": "escuela politécnica",
    "Q3803834": "instituto técnico",
    "Q7692354": "escuela técnica",
    "Q2120173": "escuela superior pedagógica",
    "Q184644": "conservatorio",
    "Q383092": "academia de bellas artes",
    "Q917182": "academia militar",
    "Q14911880": "seminario",
    "Q576603": "colegio bíblico",
    "Q12513145": "sekolah tinggi",
    "Q110296306": "junior college (Japón)",
    "Q47531586": "Institute of National Importance (India)",
}

#: Clases admitidas **solo como clase exacta**, sin sus subclases: la genérica
#: de la raíz describe a miles de instituciones que no concretan más, y vale,
#: pero su descendencia incluye media escolaridad del mundo.
ALLOWED_EXACT = {
    "Q38723": "institución educativa universitaria",
}

#: Lo que se descarta con todas sus subclases. Una facultad o una división
#: académica es **parte** de una universidad, no otra institución: sin esto la
#: Universidad Juárez de Tabasco aportaría nueve equipos a una liga en vez de
#: uno. Las academias de ciencias son sociedades de sabios: no dan clase.
#:
#: Ojo con lo que NO está aquí: un campus sí es institución aparte —el Tec de
#: Monterrey campus Chihuahua juega contra el campus Juárez—, así que la
#: relación «parte de» de Wikidata no sirve para decidir esto; hay que mirar
#: la clase.
EXCLUDED_SUBTREES = {
    "Q180958": "facultad universitaria",
    "Q20820271": "escuela de postgrado",
    "Q414147": "academia de ciencias",
}

#: Y esto no descarta por sí solo: deja de contar como prueba de que algo sea
#: educación superior, pero si la institución además declara una clase válida,
#: entra. Hace falta porque Wikidata tiene a «escuela de mujeres» colgando de
#: *college*, y por esa única arista se colaban seis mil escuelas primarias de
#: niñas de Pakistán. Un college femenino de verdad también se declara college
#: y sigue entrando; una primaria no.
SOFT_EXCLUDED_SUBTREES = {
    "Q22713629": "escuela de mujeres",
    "Q9842": "escuela primaria",
    "Q9826": "high school",
    "Q149566": "escuela media",
}

#: Y esto se descarta **solo como clase exacta**, sin tocar sus subclases: de
#: «academia» cuelgan la academia de bellas artes y la militar, que sí son
#: centros de enseñanza, mientras que una entidad declarada «academia» a secas
#: suele ser una corporación de académicos, como la Academia Mexicana de la
#: Historia.
EXCLUDED_EXACT = {
    "Q162633": "academia",
    "Q955824": "sociedad científica",
}
LICENCE = "CC0 1.0"
ATTRIBUTION = "Wikidata (https://www.wikidata.org), CC0 1.0"
DEFAULT_OUT = ROOT / "data" / "universities" / "universities.ndjson.gz"
COORDINATE = re.compile(r"^Point\((?P<lon>-?\d+(?:\.\d+)?) (?P<lat>-?\d+(?:\.\d+)?)\)$")
#: Pausa entre consultas. El servicio es gratuito y compartido: no se abusa.
PAUSE_SECONDS = 0.8
RETRIES = 3

COUNTRIES_QUERY = """
SELECT ?iso (SAMPLE(?label) AS ?name) WHERE {
  ?country wdt:P297 ?iso .
  OPTIONAL { ?country rdfs:label ?label . FILTER(lang(?label) = "es") }
}
GROUP BY ?iso
ORDER BY ?iso
"""

#: Aristas «subclase de» del árbol educativo. Filtrar dentro de la consulta de
#: cada país la vuelve lentísima (minutos por país); con el árbol en memoria la
#: consulta vuelve a costar un segundo y el criterio queda a la vista en este
#: fichero en vez de escondido en el SPARQL.
CLASS_TREE_QUERY = """
SELECT ?clase ?claseLabel ?super WHERE {
  ?clase wdt:P279* wd:Q38723 .
  OPTIONAL { ?clase wdt:P279 ?super }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "es,en". }
}
"""

INSTITUTIONS_QUERY = """
SELECT DISTINCT ?item ?itemLabel ?coord ?type ?inception ?site WHERE {{
  ?country wdt:P297 "{iso2}" .
  ?item wdt:P31/wdt:P279* wd:{root} ;
        wdt:P17 ?country ;
        wdt:P625 ?coord ;
        wdt:P31 ?type .
  OPTIONAL {{ ?item wdt:P571 ?inception }}
  OPTIONAL {{ ?item wdt:P856 ?site }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "es,en". }}
}}
"""

#: Quién cuelga de otra institución. Wikidata lo dice de dos maneras —«parte
#: de» (P361) y «organización matriz» (P749)— y hacen falta las dos: las
#: escuelas de negocios estadounidenses usan la segunda y las divisiones
#: académicas mexicanas la primera.
#:
#: Se pregunta aparte y **solo por las dudosas** —las que únicamente declaran
#: clases de parte—, que son unas decenas por país. Pedirlo para todas, dentro
#: de la consulta anterior, multiplicaba por diez lo que tardaba un país
#: grande: Estados Unidos pasaba de un minuto a no terminar.
PARTS_QUERY = """
SELECT DISTINCT ?item WHERE {{
  VALUES ?item {{ {items} }}
  {{ ?item wdt:P361 ?parent }} UNION {{ ?item wdt:P749 ?parent }}
}}
"""
#: Cuántas dudosas se preguntan de una vez.
PARTS_BATCH = 150

#: Clases que, cuando la institución es *parte de* otra, delatan que es un
#: trozo y no un centro aparte: la escuela de negocios o de medicina de una
#: universidad, su conservatorio, su colegio mayor. Si no cuelgan de nadie
#: —INSEAD, un conservatorio independiente— entran igual.
#:
#: Lo que **no** está aquí se sostiene solo aunque pertenezca a algo: un
#: instituto tecnológico es institución aunque forme parte del TecNM, y un
#: campus juega su propia liga —el campus Juárez del Tec contra el campus
#: Chihuahua—, igual que Berkeley no desaparece por ser de la Universidad de
#: California.
PART_LIKE_SUBTREES = {
    "Q1143635": "escuela de negocios",
    "Q1663017": "escuela de ingeniería",
    "Q494230": "escuela de medicina",
    "Q446901": "escuela de enfermería",
    "Q17072837": "medical college (India)",
    "Q184644": "conservatorio",
    "Q383092": "academia de bellas artes",
    "Q2680291": "colegio mayor",
    "Q20820271": "escuela de postgrado",
}


def consultar(query: str) -> list[dict[str, dict[str, str]]]:
    """Lanza una consulta SPARQL y devuelve sus filas, con reintentos."""
    data = urlencode({"query": query, "format": "json"}).encode("utf-8")
    ultimo: Exception | None = None
    for intento in range(RETRIES):
        request = Request(
            ENDPOINT,
            data=data,
            headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
        )
        try:
            with urlopen(request, timeout=120) as response:
                return json.load(response)["results"]["bindings"]
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            ultimo = error
            time.sleep(2 * (intento + 1))
    raise RuntimeError(f"la consulta falló tras {RETRIES} intentos: {ultimo}")


def clases_vigentes() -> tuple[dict[str, str], set[str], set[str], set[str]]:
    """Resuelve qué clases concretas cuentan y cuáles no.

    Wikidata no declara «universidad pública» en el catálogo: declara que es
    subclase de «universidad». Esta función baja el árbol una vez y devuelve
    los nombres de cada clase, el conjunto permitido y el excluido, ya
    expandidos a todas sus subclases.
    """
    hijos: dict[str, set[str]] = {}
    nombres: dict[str, str] = {}
    for fila in consultar(CLASS_TREE_QUERY):
        clase = fila["clase"]["value"].rsplit("/", 1)[-1]
        etiqueta = fila.get("claseLabel", {}).get("value", "").strip()
        if etiqueta and etiqueta != clase:
            nombres[clase] = etiqueta
        super_clase = fila.get("super", {}).get("value", "").rsplit("/", 1)[-1]
        if super_clase:
            hijos.setdefault(super_clase, set()).add(clase)

    def descendientes(raices: set[str]) -> set[str]:
        alcanzadas: set[str] = set()
        pendientes = list(raices)
        while pendientes:
            actual = pendientes.pop()
            if actual in alcanzadas:
                continue
            alcanzadas.add(actual)
            pendientes.extend(hijos.get(actual, ()))
        return alcanzadas

    excluidas = descendientes(set(EXCLUDED_SUBTREES))
    # Lo excluido duro manda sobre lo permitido: una división académica también
    # es «escuela» de algo. Lo blando y las clases exactas solo salen del
    # permitido, así que no tumban a una institución que además sea válida.
    fuera = excluidas | descendientes(set(SOFT_EXCLUDED_SUBTREES)) | set(EXCLUDED_EXACT)
    permitidas = (descendientes(set(ALLOWED_CLASSES)) | set(ALLOWED_EXACT)) - fuera
    autonomas = permitidas - descendientes(set(PART_LIKE_SUBTREES))
    return nombres, permitidas, excluidas, autonomas


def paises() -> list[str]:
    """Códigos ISO 3166-1 alfa-2 que Wikidata reconoce como país."""
    filas = consultar(COUNTRIES_QUERY)
    vistos = {
        fila["iso"]["value"].strip().upper()
        for fila in filas
        if len(fila["iso"]["value"].strip()) == 2
    }
    return sorted(vistos)


#: Cuánto tienen que acercarse dos fichas para sospechar que son la misma.
#: Tres milésimas de grado son unos trescientos metros: el mismo campus. Se
#: mide la distancia, no se comparan coordenadas redondeadas: 100,290 y
#: 100,291 son el mismo sitio y caerían en cubos distintos.
SAME_PLACE_DEGREES = 0.003
#: Y cuánto nombre tienen que compartir para confirmarlo.
SAME_NAME_PREFIX = 20


def fusionar_duplicados(filas: list[dict[str, object]]) -> list[dict[str, object]]:
    """Quita la ficha repetida de una misma institución.

    Wikidata describe a veces la institución y su campus principal como dos
    entidades distintas en la misma coordenada: el Tecnológico de Monterrey y
    su campus Monterrey, por ejemplo. Para una liga eso serían dos equipos del
    mismo sitio, así que se queda una. Un campus en otra ciudad no se toca:
    tiene coordenada propia y es un equipo de verdad.
    """
    from math import cos, radians

    salida: list[dict[str, object]] = []
    # Cubos de un centésimo de grado —algo más de un kilómetro— para no
    # comparar cada institución con todas las del país.
    cubos: dict[tuple[int, int], list[dict[str, object]]] = {}
    for fila in filas:
        lat, lon = float(fila["lat"]), float(fila["lon"])
        nombre = str(fila["name"]).casefold()[:SAME_NAME_PREFIX]
        escala = max(0.2, cos(radians(lat)))
        base = (int(lat * 100), int(lon * 100))
        gemela = False
        for delta_lat in (-1, 0, 1):
            for delta_lon in (-1, 0, 1):
                for otra in cubos.get((base[0] + delta_lat, base[1] + delta_lon), ()):
                    if (
                        abs(float(otra["lat"]) - lat) < SAME_PLACE_DEGREES
                        and abs(float(otra["lon"]) - lon) * escala < SAME_PLACE_DEGREES
                        and str(otra["name"]).casefold()[:SAME_NAME_PREFIX] == nombre
                    ):
                        gemela = True
                        break
                if gemela:
                    break
            if gemela:
                break
        if gemela:
            continue
        cubos.setdefault(base, []).append(fila)
        salida.append(fila)
    return salida


def _con_padre(qids: list[str]) -> set[str]:
    """Cuáles de esas entidades cuelgan de otra, por lotes."""
    salida: set[str] = set()
    for inicio in range(0, len(qids), PARTS_BATCH):
        lote = qids[inicio : inicio + PARTS_BATCH]
        filas = consultar(PARTS_QUERY.format(items=" ".join(f"wd:{qid}" for qid in lote)))
        salida.update(fila["item"]["value"].rsplit("/", 1)[-1] for fila in filas)
    return salida


def instituciones(
    iso2: str,
    nombres: dict[str, str],
    permitidas: set[str],
    excluidas: set[str],
    autonomas: set[str],
) -> list[dict[str, object]]:
    """Instituciones de educación superior de un país, deduplicadas por QID."""
    filas = consultar(INSTITUTIONS_QUERY.format(iso2=iso2, root=ROOT_CLASS))
    tipos: dict[str, set[str]] = {}
    for fila in filas:
        qid = fila.get("item", {}).get("value", "").rsplit("/", 1)[-1]
        tipo = fila.get("type", {}).get("value", "").rsplit("/", 1)[-1]
        if qid and tipo:
            tipos.setdefault(qid, set()).add(tipo)

    dudosas = sorted(
        qid for qid, propias in tipos.items() if propias & permitidas and not propias & autonomas
    )
    con_padre = _con_padre(dudosas)

    salida: dict[str, dict[str, object]] = {}
    for fila in filas:
        qid = fila.get("item", {}).get("value", "").rsplit("/", 1)[-1]
        nombre = fila.get("itemLabel", {}).get("value", "").strip()
        punto = COORDINATE.match(fila.get("coord", {}).get("value", ""))
        # Sin identidad, sin nombre o sin coordenada no hay forma honesta de
        # situarla en un territorio: se descarta en vez de aproximarla.
        if not qid or not nombre or not punto or nombre == qid:
            continue
        propias = tipos.get(qid, set())
        if propias & excluidas or not propias & permitidas:
            continue
        # Una parte de otra institución solo entra si se sostiene sola: la
        # escuela de ingeniería de una universidad, no; su campus, sí.
        if qid in con_padre and not propias & autonomas:
            continue
        registro = salida.setdefault(
            qid,
            {
                "qid": qid,
                "name": nombre,
                "country": iso2,
                "lat": round(float(punto.group("lat")), 5),
                "lon": round(float(punto.group("lon")), 5),
            },
        )
        if "type" not in registro:
            # De sus clases válidas se guarda la primera con nombre, estable
            # entre ejecuciones por ir ordenada.
            for tipo_qid in sorted(propias & permitidas):
                if tipo_qid in nombres:
                    registro["type"] = nombres[tipo_qid]
                    registro["type_qid"] = tipo_qid
                    break
        fundacion = fila.get("inception", {}).get("value", "")
        if fundacion[:4].isdigit() and "founded" not in registro:
            registro["founded"] = int(fundacion[:4])
        sitio = fila.get("site", {}).get("value", "").strip()
        if sitio and "site" not in registro:
            registro["site"] = sitio[:300]
    return fusionar_duplicados(
        sorted(salida.values(), key=lambda fila: (str(fila["name"]).casefold(), fila["qid"]))
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--only-countries", default="", help="ISO2 separados por coma; vacío = todo el mundo"
    )
    args = parser.parse_args()

    pedidos = {item.strip().upper() for item in args.only_countries.split(",") if item.strip()}
    print("resolviendo el árbol de clases educativas…", flush=True)
    nombres, permitidas, excluidas, autonomas = clases_vigentes()
    print(f"clases que cuentan: {len(permitidas)} | descartadas: {len(excluidas)}", flush=True)
    lista = sorted(pedidos) if pedidos else paises()
    print(f"países a consultar: {len(lista)}", flush=True)

    total = 0
    por_pais: dict[str, int] = {}
    fallos: list[str] = []
    # Una institución puede declarar varias nacionalidades —un campus en cada
    # país—, pero su coordenada es una sola: se escribe una vez, con el primer
    # país que la reclama, y se deja constancia de cuántas eran.
    emitidos: set[str] = set()
    repetidas = 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temporal = args.out.with_suffix(args.out.suffix + ".parcial")
    with gzip.open(temporal, "wt", encoding="utf-8", newline="\n") as salida:
        for indice, iso2 in enumerate(lista, start=1):
            try:
                filas = instituciones(iso2, nombres, permitidas, excluidas, autonomas)
            except RuntimeError as error:
                fallos.append(iso2)
                print(f"  [{indice}/{len(lista)}] {iso2}: FALLÓ ({error})", flush=True)
                continue
            nuevas = 0
            for fila in filas:
                qid = str(fila["qid"])
                if qid in emitidos:
                    repetidas += 1
                    continue
                emitidos.add(qid)
                salida.write(json.dumps(fila, ensure_ascii=False, sort_keys=True) + "\n")
                nuevas += 1
            total += nuevas
            if nuevas:
                por_pais[iso2] = nuevas
            print(f"  [{indice}/{len(lista)}] {iso2}: {nuevas}", flush=True)
            time.sleep(PAUSE_SECONDS)

    if fallos:
        # Un catálogo al que le falta un país entero no se publica como
        # completo: se dice qué falta y se deja el parcial para reintentar.
        print(f"países sin respuesta: {', '.join(fallos)}", flush=True)
    temporal.replace(args.out)

    manifiesto = args.out.with_name("MANIFEST.json")
    manifiesto.write_text(
        json.dumps(
            {
                "source": "wikidata",
                "attribution": ATTRIBUTION,
                "licence": LICENCE,
                "allowed_classes": ALLOWED_CLASSES,
                "allowed_exact": ALLOWED_EXACT,
                "soft_excluded_subtrees": SOFT_EXCLUDED_SUBTREES,
                "part_like_subtrees": PART_LIKE_SUBTREES,
                "excluded_subtrees": EXCLUDED_SUBTREES,
                "excluded_exact": EXCLUDED_EXACT,
                "resolved_classes": len(permitidas),
                "endpoint": ENDPOINT,
                "built_at": datetime.now(UTC).strftime("%Y-%m-%d"),
                "countries": len(por_pais),
                "institutions": total,
                "failed_countries": fallos,
                "multinational_duplicates": repetidas,
                "file": args.out.name,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    tamano = args.out.stat().st_size / 1_048_576
    print(f"catálogo escrito en {args.out} ({tamano:.1f} MB, {total} instituciones)")
    if not total:
        sys.exit("no se obtuvo ninguna institución: el catálogo no se ha actualizado")


if __name__ == "__main__":  # pragma: no cover - punto de entrada
    main()
