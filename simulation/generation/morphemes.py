"""Inventario de morfemas: las piezas con las que se acuñan los nombres.

Aquí **no hay nombres de clubes**. Hay raíces léxicas —`mezquite`, `salina`,
`fundición`—, el sufijo que cada una admite por clase y las plantillas
gramaticales de cada idioma. «Mezquitales del Norte» no está escrito en ningún
sitio: lo acuña `simulation.generation.morphology` combinando `mezquite`, la
clase `colectivo`, el plural y una plantilla.

Por qué importa: con una lista de apodos acabados, 96 clubes repetían «Viento»
siete veces, porque el inventario eran 24 palabras por idioma. Con 130 raíces
que admiten de una a cuatro clases de derivación, flexión de género y número y
una docena de plantillas, el espacio pasa de decenas a decenas de miles de
denominaciones **bien formadas**, y el registro del universo puede penalizar la
raíz —no sólo la cadena final— para que dos clubes no suenen a lo mismo.

Dos límites declarados, no disimulados:

- **La profundidad es por idioma.** Español e inglés tienen morfología: reglas
  de sufijación, alomorfos declarados por raíz, acentuación y fonotáctica. El
  resto de locales tiene inventario curado y ampliado, sin derivación: el motor
  no fabrica morfología ajena. Un país sin gramática curada (`und`) sigue
  recibiendo sólo su topónimo verificado.
- **El español es de México.** Es el mismo límite que ya declara
  `lexicon.py`: `huizache`, `tlacuache` o `tolvanera` son palabras de ahí.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

#: Clases de derivación que una raíz puede admitir.
#:
#: - `colectivo`: el lugar donde eso abunda (mezquite → mezquital).
#: - `agentivo`: quien trabaja o vive de eso (salina → salinero).
#: - `adjetival`: el adjetivo de relación (ribera → ribereño).
#: - `aumentativo`: la cosa desmedida (viento → ventarrón).
#: - `compuesto`: segundo elemento de un compuesto (inglés: salt + ridge).
SUFFIX_CLASSES = ("colectivo", "agentivo", "adjetival", "aumentativo", "compuesto")


@dataclass(frozen=True)
class Root:
    """Un morfema léxico con sus rasgos y los sufijos que licencia.

    `forms` no guarda palabras derivadas: guarda **qué alomorfo** toma esta raíz
    en cada clase, porque en español la elección es léxica y no se puede deducir
    (pino → pin*ar*, arena → arena*l*). Se escribe `"sufijo"` o
    `"raíz_irregular|sufijo"` cuando el tema cambia: `roble` → `"robled|al"`.
    """

    key: str
    lemma: str
    #: `m`, `f` o `n` (sin género marcado: idiomas que no lo tienen).
    gender: str
    #: Familia semántica que hereda el logo (ver `identity.semantics`).
    family: str
    #: Motivo gráfico que **dibuja** esta raíz, o `""` si ninguno la representa.
    motif: str = ""
    tags: frozenset[str] = frozenset()
    forms: Mapping[str, str] = field(default_factory=dict)
    #: Plural irregular o invariable, cuando la regla no acierta.
    plural: str = ""
    #: Si la raíz ya es plural de por sí («Correcaminos»).
    collective: bool = False

    def allomorph(self, suffix_class: str) -> tuple[str, str] | None:
        """Devuelve `(tema, sufijo)` para la clase, o `None` si no la admite."""
        declared = self.forms.get(suffix_class)
        if not declared:
            return None
        stem, _, suffix = declared.rpartition("|")
        return (stem or self.lemma, suffix)


@dataclass(frozen=True)
class Form:
    """Plantilla gramatical: cómo se presenta una institución en un idioma.

    Las ranuras declaran qué pide cada hueco, de modo que la concordancia sea
    una regla y no una coincidencia: `Unión {adj_f}` → «Unión Salinera», y
    `Deportivo {adj_m}` → «Deportivo Salinero», de la misma raíz.
    """

    kind: str
    pattern: str
    #: Épocas que prefieren esta forma. Vacío: cualquiera.
    eras: frozenset[str] = frozenset()
    #: Vetas que la habilitan. Vacío: cualquiera.
    vetas: frozenset[str] = frozenset()
    #: Peso relativo dentro del idioma.
    weight: float = 1.0


@dataclass(frozen=True)
class LocaleLexicon:
    """Todo lo que el motor sabe decir en un idioma."""

    locale: str
    roots: tuple[Root, ...]
    forms: tuple[Form, ...]
    #: Modificadores combinables, con la preposición ya resuelta.
    qualifiers: tuple[str, ...] = ()
    #: `True` sólo donde hay reglas de derivación implementadas y revisadas.
    derives: bool = False


def _key(lemma: str) -> str:
    import unicodedata

    plain = "".join(
        c for c in unicodedata.normalize("NFKD", lemma.casefold()) if not unicodedata.combining(c)
    )
    return plain.replace(" ", "_")


def _r(
    lemma: str,
    gender: str,
    family: str,
    motif: str = "",
    tags: str = "",
    *,
    plural: str = "",
    collective: bool = False,
    **forms: str,
) -> Root:
    """Atajo de lectura para el inventario. `forms` son clases de sufijo."""
    desconocidas = set(forms) - set(SUFFIX_CLASSES)
    if desconocidas:
        raise ValueError(f"clase de sufijo inexistente en {lemma}: {sorted(desconocidas)}")
    return Root(
        key=_key(lemma),
        lemma=lemma,
        gender=gender,
        family=family,
        motif=motif,
        tags=frozenset(tags.split()),
        forms={clase: valor for clase, valor in forms.items() if valor},
        plural=plural,
        collective=collective,
    )


# --- Español (de México) ------------------------------------------------------
#
# Cada alomorfo está comprobado uno a uno: `barranca` + `agentivo` da
# «barranquero» por la regla c→qu, no porque la palabra esté escrita aquí.
_ES_ROOTS: tuple[Root, ...] = (
    # Terreno
    _r("médano", "m", "nature", "wave", "terreno arido", agentivo="ero"),
    _r("duna", "f", "nature", "wave", "terreno arido costa"),
    _r("barranca", "f", "nature", "", "terreno", colectivo="al", agentivo="ero"),
    _r("cañón", "m", "nature", "", "terreno", agentivo="ero"),
    _r("sierra", "f", "nature", "summit", "terreno altura", adjetival="serr|ano"),
    _r("cerro", "m", "nature", "summit", "terreno altura"),
    _r("meseta", "f", "nature", "summit", "terreno altura"),
    _r("risco", "m", "nature", "summit", "terreno altura"),
    _r("llano", "m", "nature", "", "terreno rural", agentivo="ero"),
    _r("vega", "f", "nature", "", "terreno agua rural", agentivo="ero"),
    _r("ciénaga", "f", "nature", "", "terreno agua tropical"),
    _r("salina", "f", "nature", "", "terreno arido costa", agentivo="ero", adjetival="ero"),
    _r("peñasco", "m", "nature", "", "terreno altura", colectivo="al"),
    _r("arena", "f", "nature", "wave", "terreno arido costa", colectivo="al", adjetival="oso"),
    _r("vado", "m", "nature", "", "terreno agua"),
    _r("cuesta", "f", "nature", "summit", "terreno altura"),
    _r("páramo", "m", "nature", "", "terreno altura frio"),
    # Agua
    _r("río", "m", "nature", "river", "agua"),
    _r("arroyo", "m", "nature", "river", "agua rural"),
    _r("ribera", "f", "nature", "river", "agua", adjetival="eño"),
    _r("acequia", "f", "nature", "river", "agua rural", agentivo="ero"),
    _r("estero", "m", "nature", "wave", "agua tropical costa"),
    _r("marea", "f", "nature", "wave", "agua costa", agentivo="ante"),
    _r("laguna", "f", "nature", "wave", "agua", agentivo="ero"),
    _r("manantial", "m", "nature", "river", "agua"),
    _r("presa", "f", "steadfast", "", "agua"),
    _r("cauce", "m", "nature", "river", "agua"),
    # Flora
    _r("mezquite", "m", "nature", "", "flora arido", colectivo="al"),
    _r("nopal", "m", "nature", "cactus", "flora arido", colectivo="era"),
    _r("huizache", "m", "nature", "", "flora arido", colectivo="al"),
    _r("cardón", "m", "nature", "cactus", "flora arido", colectivo="al"),
    _r("maguey", "m", "nature", "cactus", "flora arido", colectivo="al"),
    _r("agave", "m", "nature", "cactus", "flora arido"),
    _r("roble", "m", "nature", "oak", "flora", colectivo="robled|al"),
    _r("encina", "f", "nature", "oak", "flora", colectivo="ar"),
    _r("pino", "m", "nature", "pine", "flora altura frio", colectivo="ar"),
    _r("abeto", "m", "nature", "pine", "flora altura frio"),
    _r("álamo", "m", "nature", "oak", "flora", colectivo="eda"),
    _r("sauce", "m", "nature", "oak", "flora agua", colectivo="sauced|al"),
    _r("carrizo", "m", "nature", "", "flora agua", colectivo="al"),
    _r("junco", "m", "nature", "", "flora agua", colectivo="al"),
    _r("tule", "m", "nature", "", "flora agua", colectivo="ar"),
    _r("caña", "f", "nature", "", "flora tropical", colectivo="cañav|eral", agentivo="ero"),
    _r("palma", "f", "nature", "pine", "flora tropical costa", colectivo="ar", agentivo="ero"),
    _r("ceiba", "f", "nature", "oak", "flora tropical", colectivo="al"),
    _r("guayacán", "m", "nature", "oak", "flora tropical", colectivo="al"),
    _r("higuera", "f", "nature", "", "flora", colectivo="al"),
    _r("nogal", "m", "nature", "oak", "flora", colectivo="era"),
    _r("chaparro", "m", "nature", "", "flora arido", colectivo="al"),
    _r("mata", "f", "nature", "", "flora arido", colectivo="mator|ral"),
    _r("espina", "f", "bold", "", "flora arido", colectivo="al"),
    _r("rosa", "f", "nature", "rose", "flora", colectivo="al"),
    _r("girasol", "m", "nature", "sun", "flora rural"),
    _r("trigo", "m", "community", "wheat", "flora rural abstracto", colectivo="al"),
    _r("maíz", "m", "community", "wheat", "flora rural", colectivo="al"),
    # Fauna
    _r("halcón", "m", "ambition", "bird", "fauna"),
    _r("tecolote", "m", "ambition", "bird", "fauna"),
    _r("cuervo", "m", "ambition", "bird", "fauna"),
    _r("zopilote", "m", "ambition", "bird", "fauna arido"),
    _r("garza", "f", "ambition", "bird", "fauna agua"),
    _r("golondrina", "f", "ambition", "bird", "fauna"),
    _r("cenzontle", "m", "ambition", "bird", "fauna"),
    _r("águila", "f", "ambition", "bird", "fauna altura"),
    _r(
        "correcaminos",
        "m",
        "ambition",
        "bird",
        "fauna arido",
        plural="Correcaminos",
        collective=True,
    ),
    _r("lobo", "m", "bold", "jaguar", "fauna frio"),
    _r("coyote", "m", "bold", "jaguar", "fauna arido"),
    _r("puma", "m", "bold", "jaguar", "fauna altura"),
    _r("jabalí", "m", "bold", "jaguar", "fauna tropical"),
    _r("toro", "m", "bold", "bull", "fauna rural", agentivo="ero"),
    _r("alacrán", "m", "bold", "", "fauna arido"),
    _r("venado", "m", "nature", "", "fauna"),
    _r("berrendo", "m", "nature", "", "fauna arido"),
    _r("liebre", "f", "nature", "", "fauna arido"),
    _r("tejón", "m", "nature", "", "fauna"),
    _r("mapache", "m", "nature", "", "fauna"),
    _r("tlacuache", "m", "nature", "", "fauna"),
    _r("murciélago", "m", "bold", "", "fauna"),
    _r("chapulín", "m", "bold", "", "fauna rural"),
    # Clima
    _r("norte", "m", "bold", "", "clima abstracto"),
    _r("viento", "m", "nature", "", "clima", aumentativo="vent|arrón"),
    _r("tolvanera", "f", "bold", "", "clima arido abstracto"),
    _r("aguacero", "m", "bold", "", "clima tropical"),
    _r("canícula", "f", "bold", "", "clima arido tropical abstracto"),
    _r("neblina", "f", "nature", "", "clima altura frio abstracto"),
    _r("bruma", "f", "nature", "", "clima costa frio"),
    _r("relámpago", "m", "bold", "bolt", "clima tropical"),
    _r("granizo", "m", "bold", "", "clima altura frio abstracto", colectivo="ada"),
    _r("helada", "f", "steadfast", "", "clima frio altura abstracto"),
    _r("levante", "m", "nature", "", "clima costa abstracto"),
    _r("poniente", "m", "nature", "", "clima abstracto"),
    _r("solano", "m", "nature", "sun", "clima arido"),
    _r("sol", "m", "nature", "sun", "clima", colectivo="ana"),
    _r("rayo", "m", "bold", "bolt", "clima"),
    _r("tormenta", "f", "bold", "", "clima"),
    _r("ventisca", "f", "bold", "", "clima frio"),
    _r("marejada", "f", "bold", "wave", "clima costa"),
)

# Raíces de valor, con la época que las usaba. Un club de 1912 no se llama como
# uno de 2018: las sociedades mutualistas hablaban de porvenir y fraternidad,
# y la marca contemporánea prefiere una palabra sola y corta.
_ES_VALUES: tuple[Root, ...] = (
    _r("unión", "f", "community", "", "valor mutualista moderna abstracto"),
    _r("alianza", "f", "community", "bridge", "valor mutualista moderna abstracto"),
    _r("fraternidad", "f", "community", "", "valor mutualista abstracto"),
    _r("mutualidad", "f", "community", "", "valor mutualista abstracto"),
    _r("porvenir", "m", "ambition", "", "valor mutualista abstracto"),
    _r("progreso", "m", "ambition", "", "valor mutualista moderna abstracto"),
    _r("esfuerzo", "m", "steadfast", "anvil", "valor mutualista abstracto"),
    _r("ideal", "m", "ambition", "", "valor mutualista abstracto"),
    _r("aurora", "f", "cosmic", "sun", "valor mutualista abstracto"),
    _r("libertad", "f", "ambition", "crown", "valor mutualista moderna abstracto"),
    _r("juventud", "f", "community", "", "valor mutualista moderna abstracto"),
    _r("centenario", "m", "community", "", "valor moderna abstracto"),
    _r("vanguardia", "f", "ambition", "", "valor moderna expansion abstracto"),
    _r("impulso", "m", "ambition", "", "valor moderna expansion abstracto"),
    _r("pionero", "m", "community", "", "valor moderna"),
    _r("poblador", "m", "community", "home_plate", "valor moderna"),
    _r("centinela", "m", "steadfast", "tower", "valor moderna expansion"),
    _r("vigía", "m", "steadfast", "tower", "valor moderna"),
    _r("farol", "m", "steadfast", "tower", "valor moderna urbano", agentivo="ero"),
    _r("frontera", "f", "community", "bridge", "valor moderna", adjetival="izo"),
    _r("puente", "m", "community", "bridge", "valor moderna urbano"),
    _r("camino", "m", "community", "", "valor moderna", agentivo="ante"),
    _r("raíz", "f", "community", "oak", "valor mutualista contemporanea"),
    _r("barrio", "m", "community", "home_plate", "valor moderna expansion urbano abstracto"),
    _r("pueblo", "m", "community", "home_plate", "valor mutualista moderna rural abstracto"),
    _r("bastión", "m", "steadfast", "shield_boss", "valor expansion"),
    _r("guardián", "m", "steadfast", "shield_boss", "valor expansion contemporanea"),
    _r("yunque", "m", "steadfast", "anvil", "valor expansion"),
    _r("hierro", "m", "steadfast", "anvil", "valor expansion abstracto", agentivo="herr|ero"),
    _r("acero", "m", "steadfast", "anvil", "valor expansion contemporanea abstracto"),
    _r("fuego", "m", "bold", "flame", "valor expansion contemporanea abstracto"),
    _r("furia", "f", "bold", "flame", "valor expansion contemporanea abstracto"),
    _r("ímpetu", "m", "bold", "", "valor contemporanea abstracto"),
    _r("cumbre", "f", "ambition", "summit", "valor expansion contemporanea"),
    _r("horizonte", "m", "ambition", "", "valor expansion contemporanea abstracto"),
    _r("imperio", "m", "ambition", "crown", "valor expansion abstracto"),
    _r("corona", "f", "ambition", "crown", "valor expansion"),
    _r("torre", "f", "steadfast", "tower", "valor expansion urbano"),
    _r("estrella", "f", "cosmic", "star", "valor moderna expansion"),
    _r("lucero", "m", "cosmic", "star", "valor mutualista moderna"),
    _r("cometa", "m", "cosmic", "comet", "valor expansion contemporanea"),
    _r("luna", "f", "cosmic", "moon", "valor contemporanea abstracto"),
    _r("eclipse", "m", "cosmic", "moon", "valor contemporanea"),
    _r("alba", "f", "cosmic", "sun", "valor mutualista contemporanea abstracto"),
    _r("Orión", "m", "cosmic", "constellation", "valor contemporanea"),
    _r("Lira", "f", "cosmic", "constellation", "valor mutualista contemporanea"),
    _r("Auriga", "m", "cosmic", "constellation", "valor contemporanea"),
    _r("Sirio", "m", "cosmic", "constellation", "valor contemporanea"),
)

# Oficios: entran por la veta de patronazgo —la casa, el socio o la empresa que
# sostiene al club— y por eso llevan el gremio, no el índice económico del
# territorio.
_ES_TRADES: tuple[Root, ...] = (
    _r("fundición", "f", "steadfast", "anvil", "oficio", agentivo="fundid|or"),
    _r("molino", "m", "steadfast", "gear", "oficio", agentivo="ero"),
    _r("mina", "f", "steadfast", "gear", "oficio", agentivo="ero"),
    _r("cerveza", "f", "community", "wheat", "oficio", agentivo="ero"),
    _r("ferrocarril", "m", "steadfast", "gear", "oficio", adjetival="ferrovi|ario"),
    _r("tranvía", "m", "steadfast", "gear", "oficio urbano", adjetival="tranvi|ario"),
    _r("hojalata", "f", "steadfast", "anvil", "oficio", agentivo="ero"),
    _r("vidrio", "m", "steadfast", "", "oficio", agentivo="ero"),
    _r("ladrillo", "m", "steadfast", "", "oficio", agentivo="ero"),
    _r("horno", "m", "steadfast", "anvil", "oficio", agentivo="ero"),
    _r("estiba", "f", "steadfast", "", "oficio costa", agentivo="dor"),
    _r("pan", "m", "community", "wheat", "oficio", agentivo="panad|ero"),
    _r("azúcar", "m", "community", "wheat", "oficio tropical", agentivo="ero"),
    _r("cal", "f", "steadfast", "", "oficio", agentivo="ero"),
    _r("alfarero", "m", "steadfast", "", "oficio"),
    _r("curtidor", "m", "steadfast", "", "oficio"),
    _r("tipógrafo", "m", "community", "", "oficio urbano"),
    _r("carpintero", "m", "steadfast", "oak", "oficio"),
    _r("albañil", "m", "steadfast", "", "oficio"),
    _r("tejedor", "m", "community", "", "oficio"),
    _r("maquilero", "m", "community", "gear", "oficio urbano"),
)

# Plantillas del español. Las ranuras declaran lo que piden, y por eso la
# concordancia es una regla: `Unión {adj_f}` da «Unión Salinera» y
# `Deportivo {adj_m}` da «Deportivo Salinero» desde la misma raíz. Un sustantivo
# no concuerda con la cabeza —«Club Nopalera» es correcto—, un adjetivo sí.
_ES_FORMS: tuple[Form, ...] = (
    Form("symbolic", "{nouns}", weight=2.4),
    Form("symbolic", "{noun}", weight=1.1),
    Form("relational", "{nouns} de {place}", weight=1.9),
    Form("relational", "{noun} de {place}", weight=0.7),
    Form("institutional", "Club {noun}", weight=1.0),
    Form("institutional", "Club Deportivo {nouns}", weight=0.7),
    Form("institutional", "Deportivo {adj_m}", weight=0.9),
    Form("institutional", "Atlético {adj_m}", weight=0.6),
    Form("institutional", "Asociación Deportiva {noun}", weight=0.5),
    Form("institutional", "Unión {adj_f}", weight=0.9, eras=frozenset({"mutualista", "moderna"})),
    Form("institutional", "Alianza {adj_f}", weight=0.5, eras=frozenset({"mutualista"})),
    Form(
        "institutional",
        "Sociedad Deportiva {adj_f}",
        weight=0.5,
        eras=frozenset({"mutualista", "moderna"}),
    ),
    Form(
        "institutional",
        "Juventud {adj_f}",
        weight=0.5,
        eras=frozenset({"mutualista", "moderna"}),
    ),
    Form(
        "institutional",
        "Club Social y Deportivo {noun}",
        weight=0.35,
        eras=frozenset({"mutualista"}),
    ),
    Form("territorial", "Club {place}", weight=0.8),
    Form("territorial", "Deportivo {place}", weight=0.6),
    Form("territorial", "Atlético {place}", weight=0.6),
    Form("territorial", "Asociación Deportiva {place}", weight=0.4),
    # Patronazgo: la casa, el socio o la empresa que sostiene al club.
    Form("institutional", "Deportivo {patron}", weight=1.3, vetas=frozenset({"patronazgo"})),
    Form("institutional", "Club {patron}", weight=1.0, vetas=frozenset({"patronazgo"})),
    Form(
        "institutional",
        "Club Deportivo {patron} Hermanos",
        weight=0.4,
        vetas=frozenset({"patronazgo"}),
    ),
    Form("institutional", "Fundación {patron}", weight=0.35, vetas=frozenset({"patronazgo"})),
    Form("relational", "{nouns} de la Casa {patron}", weight=0.8, vetas=frozenset({"patronazgo"})),
    Form("relational", "{nouns} {patron}", weight=0.7, vetas=frozenset({"patronazgo"})),
)

_ES_QUALIFIERS = (
    "del Norte",
    "del Sur",
    "del Alba",
    "del Valle",
    "del Río",
    "de la Sierra",
    "del Llano",
)

# --- Inglés -------------------------------------------------------------------
#
# El inglés compone: un modificador y una cabeza plural —«Salt Hawks»— es la
# construcción viva del béisbol estadounidense, y da miles de apodos con
# cuarenta raíces. La derivación agentiva (-er) se declara por raíz, igual que
# en español, porque tampoco es automática: `mill` → miller, pero no `salt` →
# *salter*.
_EN_ROOTS: tuple[Root, ...] = (
    # Cabezas: fauna y oficio, lo que la gente grita desde la grada.
    _r("hawk", "n", "ambition", "bird", "fauna cabeza"),
    _r("falcon", "n", "ambition", "bird", "fauna cabeza"),
    _r("heron", "n", "ambition", "bird", "fauna agua cabeza"),
    _r("crane", "n", "ambition", "bird", "fauna agua cabeza"),
    _r("owl", "n", "ambition", "bird", "fauna cabeza"),
    _r("wolf", "n", "bold", "jaguar", "fauna frio cabeza", plural="Wolves"),
    _r("coyote", "n", "bold", "jaguar", "fauna arido cabeza"),
    _r("badger", "n", "nature", "", "fauna cabeza"),
    _r("elk", "n", "nature", "", "fauna frio cabeza"),
    _r("bison", "n", "bold", "bull", "fauna rural cabeza", plural="Bison"),
    _r("bull", "n", "bold", "bull", "fauna rural cabeza"),
    _r("jackrabbit", "n", "nature", "", "fauna arido cabeza"),
    _r("rattler", "n", "bold", "", "fauna arido cabeza"),
    _r("miller", "n", "steadfast", "gear", "oficio cabeza"),
    _r("smith", "n", "steadfast", "anvil", "oficio cabeza"),
    _r("brewer", "n", "community", "wheat", "oficio cabeza"),
    _r("quarrier", "n", "steadfast", "", "oficio cabeza"),
    _r("harvester", "n", "community", "wheat", "oficio rural cabeza"),
    _r("pioneer", "n", "community", "", "valor moderna cabeza"),
    _r("sentinel", "n", "steadfast", "tower", "valor moderna cabeza"),
    _r("guardian", "n", "steadfast", "shield_boss", "valor expansion cabeza"),
    _r("drifter", "n", "nature", "", "valor expansion cabeza"),
    _r("lantern", "n", "steadfast", "tower", "valor moderna urbano cabeza"),
    _r("comet", "n", "cosmic", "comet", "valor contemporanea cabeza"),
    _r("meteor", "n", "cosmic", "comet", "valor contemporanea cabeza"),
    _r("star", "n", "cosmic", "star", "valor moderna cabeza"),
    _r("flame", "n", "bold", "flame", "valor contemporanea cabeza"),
    _r("bolt", "n", "bold", "bolt", "clima contemporanea cabeza"),
    _r("wave", "n", "nature", "wave", "agua costa cabeza"),
    _r("oak", "n", "nature", "oak", "flora cabeza"),
    _r("pine", "n", "nature", "pine", "flora frio cabeza"),
    # Modificadores: lo que el territorio pone delante.
    _r("salt", "n", "steadfast", "", "terreno arido costa modificador abstracto"),
    _r("iron", "n", "steadfast", "anvil", "oficio modificador"),
    _r("stone", "n", "steadfast", "", "terreno modificador"),
    _r("timber", "n", "nature", "oak", "flora modificador"),
    _r("river", "n", "nature", "river", "agua modificador"),
    _r("creek", "n", "nature", "river", "agua rural modificador"),
    _r("tide", "n", "nature", "wave", "agua costa modificador"),
    _r("harbor", "n", "community", "bridge", "agua costa urbano modificador"),
    _r("dune", "n", "nature", "wave", "terreno arido costa modificador"),
    _r("sand", "n", "nature", "wave", "terreno arido modificador"),
    _r("mesa", "n", "nature", "summit", "terreno altura arido modificador"),
    _r("ridge", "n", "nature", "summit", "terreno altura modificador"),
    _r("summit", "n", "ambition", "summit", "terreno altura modificador"),
    _r("canyon", "n", "nature", "", "terreno modificador"),
    _r("marsh", "n", "nature", "", "terreno agua modificador"),
    _r("prairie", "n", "nature", "wheat", "terreno rural modificador"),
    _r("sage", "n", "nature", "", "flora arido modificador"),
    _r("mesquite", "n", "nature", "", "flora arido modificador"),
    _r("cedar", "n", "nature", "pine", "flora modificador"),
    _r("thunder", "n", "bold", "bolt", "clima tropical modificador abstracto"),
    _r("frost", "n", "steadfast", "", "clima frio modificador abstracto"),
    _r("dust", "n", "bold", "", "clima arido modificador abstracto"),
    _r("north", "n", "bold", "", "clima frio modificador abstracto"),
    _r("mill", "n", "steadfast", "gear", "oficio modificador"),
    _r("forge", "n", "steadfast", "anvil", "oficio modificador", agentivo="forg|er"),
    _r("rail", "n", "steadfast", "gear", "oficio urbano modificador"),
    _r("union", "n", "community", "", "valor mutualista modificador abstracto"),
    _r("liberty", "n", "ambition", "crown", "valor mutualista modificador abstracto"),
    _r("dawn", "n", "cosmic", "sun", "valor mutualista modificador abstracto"),
)

_EN_FORMS: tuple[Form, ...] = (
    Form("relational", "{place} {nouns}", weight=2.6),
    Form("symbolic", "{nouns}", weight=1.0),
    Form("institutional", "{place} {nouns} Baseball Club", weight=0.5),
    Form("territorial", "{place} Baseball Club", weight=0.7),
    Form("territorial", "{place} Athletic Association", weight=0.4),
    Form("institutional", "{patron} {nouns}", weight=1.1, vetas=frozenset({"patronazgo"})),
    Form("institutional", "{patron} Athletic Club", weight=0.6, vetas=frozenset({"patronazgo"})),
    Form(
        "institutional",
        "{patron} & Sons {nouns}",
        weight=0.35,
        vetas=frozenset({"patronazgo"}),
    ),
)

# --- Idiomas con inventario curado -------------------------------------------
#
# Sin reglas de derivación: estas raíces se usan tal cual. El inventario se
# amplió de cuatro palabras por familia a entre ocho y catorce, que es lo que
# evita la repetición sin inventar morfología de un idioma que el motor no sabe
# conjugar. Todas son palabras corrientes del idioma, no marcas ni nombres de
# clubes existentes.


def _curated(entries: tuple[tuple[str, str, str, str], ...]) -> tuple[Root, ...]:
    return tuple(_r(lemma, "n", family, motif, tags) for lemma, family, motif, tags in entries)


_PT_ROOTS = _curated(
    (
        ("União", "community", "", "valor mutualista moderna"),
        ("Aliança", "community", "bridge", "valor mutualista"),
        ("Fraternidade", "community", "", "valor mutualista"),
        ("Juventude", "community", "", "valor mutualista moderna"),
        ("Bairro", "community", "home_plate", "valor moderna urbano"),
        ("Povo", "community", "home_plate", "valor mutualista rural"),
        ("Raízes", "community", "oak", "valor contemporanea"),
        ("Ponte", "community", "bridge", "valor moderna urbano"),
        ("Esperança", "ambition", "", "valor mutualista"),
        ("Progresso", "ambition", "", "valor mutualista moderna"),
        ("Porvir", "ambition", "", "valor mutualista"),
        ("Horizonte", "ambition", "", "valor expansion contemporanea"),
        ("Cume", "ambition", "summit", "valor expansion"),
        ("Vanguarda", "ambition", "", "valor moderna expansion"),
        ("Império", "ambition", "crown", "valor expansion"),
        ("Coroa", "ambition", "crown", "valor expansion"),
        ("Glória", "ambition", "crown", "valor moderna"),
        ("Fogo", "bold", "flame", "valor expansion contemporanea"),
        ("Fúria", "bold", "flame", "valor contemporanea"),
        ("Tempestade", "bold", "", "clima"),
        ("Trovão", "bold", "bolt", "clima tropical"),
        ("Raio", "bold", "bolt", "clima"),
        ("Maré", "nature", "wave", "agua costa"),
        ("Bastião", "steadfast", "shield_boss", "valor expansion"),
        ("Sentinela", "steadfast", "tower", "valor moderna"),
        ("Guardiões", "steadfast", "shield_boss", "valor expansion"),
        ("Bigorna", "steadfast", "anvil", "oficio"),
        ("Aço", "steadfast", "anvil", "valor expansion"),
        ("Ferro", "steadfast", "anvil", "oficio"),
        ("Carvalhos", "nature", "oak", "flora"),
        ("Pinheiros", "nature", "pine", "flora frio"),
        ("Cedros", "nature", "pine", "flora"),
        ("Palmeiras", "nature", "pine", "flora tropical costa"),
        ("Canavial", "nature", "", "flora tropical rural"),
        ("Mangue", "nature", "", "terreno agua tropical"),
        ("Serra", "nature", "summit", "terreno altura"),
        ("Rio", "nature", "river", "agua"),
        ("Riacho", "nature", "river", "agua rural"),
        ("Nascente", "nature", "river", "agua"),
        ("Vento", "nature", "", "clima"),
        ("Duna", "nature", "wave", "terreno arido costa"),
        ("Areia", "nature", "wave", "terreno costa"),
        ("Pedra", "steadfast", "", "terreno"),
        ("Sol", "nature", "sun", "clima"),
        ("Alvorada", "cosmic", "sun", "valor mutualista"),
        ("Estrela", "cosmic", "star", "valor moderna"),
        ("Cometa", "cosmic", "comet", "valor contemporanea"),
        ("Lua", "cosmic", "moon", "valor contemporanea"),
        ("Órion", "cosmic", "constellation", "valor contemporanea"),
        ("Lira", "cosmic", "constellation", "valor contemporanea"),
        ("Auriga", "cosmic", "constellation", "valor contemporanea"),
        ("Moinho", "steadfast", "gear", "oficio"),
        ("Fundição", "steadfast", "anvil", "oficio"),
        ("Ferroviários", "steadfast", "gear", "oficio urbano"),
        ("Cervejeiros", "community", "wheat", "oficio"),
        ("Estivadores", "steadfast", "", "oficio costa"),
        ("Oleiros", "steadfast", "", "oficio"),
    )
)

_JA_ROOTS = _curated(
    (
        ("結束", "community", "", "valor mutualista"),
        ("郷土", "community", "home_plate", "valor mutualista rural"),
        ("絆", "community", "", "valor contemporanea"),
        ("仲間", "community", "", "valor moderna"),
        ("大地", "community", "wheat", "terreno rural"),
        ("稲穂", "community", "wheat", "flora rural"),
        ("港", "community", "bridge", "agua costa urbano"),
        ("飛翔", "ambition", "bird", "valor moderna"),
        ("頂点", "ambition", "summit", "valor expansion"),
        ("開拓", "ambition", "", "valor moderna"),
        ("開拓者", "ambition", "", "valor moderna"),
        ("栄光", "ambition", "crown", "valor moderna"),
        ("鷹", "ambition", "bird", "fauna"),
        ("隼", "ambition", "bird", "fauna"),
        ("烈火", "bold", "flame", "valor expansion"),
        ("雷鳴", "bold", "bolt", "clima tropical"),
        ("雷光", "bold", "bolt", "clima"),
        ("疾風", "bold", "", "clima"),
        ("嵐", "bold", "", "clima costa"),
        ("荒波", "bold", "wave", "agua costa"),
        ("狼", "bold", "jaguar", "fauna frio"),
        ("熊", "bold", "jaguar", "fauna frio"),
        ("城塞", "steadfast", "shield_boss", "valor expansion"),
        ("守護者", "steadfast", "shield_boss", "valor expansion"),
        ("不動", "steadfast", "", "valor expansion"),
        ("不屈", "steadfast", "", "valor expansion"),
        ("黒鉄", "steadfast", "anvil", "oficio"),
        ("鉄路", "steadfast", "gear", "oficio urbano"),
        ("塩田", "steadfast", "", "terreno arido costa oficio"),
        ("昴", "cosmic", "constellation", "valor contemporanea"),
        ("北斗", "cosmic", "constellation", "valor contemporanea"),
        ("彗星", "cosmic", "comet", "valor contemporanea"),
        ("天狼", "cosmic", "constellation", "valor contemporanea"),
        ("流星", "cosmic", "comet", "valor contemporanea"),
        ("銀河", "cosmic", "star", "valor contemporanea"),
        ("暁", "cosmic", "sun", "valor mutualista"),
        ("曙", "cosmic", "sun", "valor mutualista"),
        ("山嶺", "nature", "summit", "terreno altura"),
        ("峰", "nature", "summit", "terreno altura"),
        ("渓谷", "nature", "", "terreno altura"),
        ("大河", "nature", "river", "agua"),
        ("清流", "nature", "river", "agua"),
        ("潮風", "nature", "wave", "agua costa"),
        ("朝日", "nature", "sun", "clima"),
        ("霧", "nature", "", "clima altura frio"),
        ("砂丘", "nature", "wave", "terreno arido costa"),
        ("松", "nature", "pine", "flora frio"),
        ("杉", "nature", "pine", "flora"),
        ("桜", "nature", "rose", "flora"),
    )
)

_DE_ROOTS = _curated(
    (
        ("Eintracht", "community", "", "valor mutualista moderna"),
        ("Heimat", "community", "home_plate", "valor mutualista rural"),
        ("Gemeinschaft", "community", "", "valor mutualista"),
        ("Bund", "community", "", "valor mutualista"),
        ("Freundschaft", "community", "", "valor mutualista"),
        ("Konkordia", "community", "bridge", "valor mutualista"),
        ("Einheit", "community", "", "valor mutualista moderna"),
        ("Brücke", "community", "bridge", "valor moderna urbano"),
        ("Jugend", "community", "", "valor mutualista moderna"),
        ("Aufstieg", "ambition", "", "valor moderna"),
        ("Gipfel", "ambition", "summit", "valor expansion"),
        ("Vorwärts", "ambition", "", "valor mutualista moderna"),
        ("Ruhm", "ambition", "crown", "valor moderna"),
        ("Hoffnung", "ambition", "", "valor mutualista"),
        ("Zukunft", "ambition", "", "valor moderna"),
        ("Fortschritt", "ambition", "", "valor mutualista moderna"),
        ("Freiheit", "ambition", "crown", "valor mutualista"),
        ("Adler", "ambition", "bird", "fauna altura"),
        ("Falke", "ambition", "bird", "fauna"),
        ("Sturm", "bold", "", "clima"),
        ("Donner", "bold", "bolt", "clima"),
        ("Flamme", "bold", "flame", "valor expansion"),
        ("Blitz", "bold", "bolt", "clima"),
        ("Hagel", "bold", "", "clima frio altura"),
        ("Wolf", "bold", "jaguar", "fauna frio"),
        ("Bär", "bold", "jaguar", "fauna frio"),
        ("Keiler", "bold", "jaguar", "fauna"),
        ("Bollwerk", "steadfast", "shield_boss", "valor expansion"),
        ("Wächter", "steadfast", "tower", "valor expansion"),
        ("Eisen", "steadfast", "anvil", "oficio"),
        ("Hammer", "steadfast", "anvil", "oficio"),
        ("Schmiede", "steadfast", "anvil", "oficio"),
        ("Hütte", "steadfast", "anvil", "oficio"),
        ("Mühle", "steadfast", "gear", "oficio"),
        ("Bahn", "steadfast", "gear", "oficio urbano"),
        ("Anker", "steadfast", "", "agua costa oficio"),
        ("Frost", "steadfast", "", "clima frio"),
        ("Saline", "steadfast", "", "terreno arido oficio"),
        ("Orion", "cosmic", "constellation", "valor contemporanea"),
        ("Polarstern", "cosmic", "star", "valor contemporanea"),
        ("Komet", "cosmic", "comet", "valor contemporanea"),
        ("Sirius", "cosmic", "constellation", "valor contemporanea"),
        ("Nordlicht", "cosmic", "star", "clima frio"),
        ("Morgenröte", "cosmic", "sun", "valor mutualista"),
        ("Stern", "cosmic", "star", "valor moderna"),
        ("Berge", "nature", "summit", "terreno altura"),
        ("Fels", "nature", "summit", "terreno altura"),
        ("Tal", "nature", "", "terreno"),
        ("Heide", "nature", "", "terreno rural"),
        ("Moor", "nature", "", "terreno agua"),
        ("Düne", "nature", "wave", "terreno costa arido"),
        ("Strom", "nature", "river", "agua"),
        ("Quelle", "nature", "river", "agua"),
        ("Flut", "nature", "wave", "agua costa"),
        ("Wind", "nature", "", "clima"),
        ("Nebel", "nature", "", "clima frio altura"),
        ("Sonne", "nature", "sun", "clima"),
        ("Eichen", "nature", "oak", "flora"),
        ("Buche", "nature", "oak", "flora"),
        ("Linde", "nature", "oak", "flora"),
        ("Tanne", "nature", "pine", "flora frio"),
        ("Birke", "nature", "pine", "flora frio"),
        ("Weide", "nature", "oak", "flora agua"),
    )
)

_FR_ROOTS = _curated(
    (
        ("Union", "community", "", "valor mutualista moderna"),
        ("Entente", "community", "bridge", "valor mutualista"),
        ("Concorde", "community", "bridge", "valor mutualista"),
        ("Fraternité", "community", "", "valor mutualista"),
        ("Quartier", "community", "home_plate", "valor moderna urbano"),
        ("Peuple", "community", "home_plate", "valor mutualista"),
        ("Racines", "community", "oak", "valor contemporanea"),
        ("Jeunesse", "community", "", "valor mutualista moderna"),
        ("Pont", "community", "bridge", "valor moderna urbano"),
        ("Horizon", "ambition", "", "valor expansion"),
        ("Sommet", "ambition", "summit", "valor expansion"),
        ("Avant-garde", "ambition", "", "valor moderna"),
        ("Gloire", "ambition", "crown", "valor moderna"),
        ("Espérance", "ambition", "", "valor mutualista"),
        ("Avenir", "ambition", "", "valor mutualista"),
        ("Progrès", "ambition", "", "valor mutualista moderna"),
        ("Liberté", "ambition", "crown", "valor mutualista"),
        ("Aigle", "ambition", "bird", "fauna altura"),
        ("Faucon", "ambition", "bird", "fauna"),
        ("Héron", "ambition", "bird", "fauna agua"),
        ("Flamme", "bold", "flame", "valor expansion"),
        ("Orage", "bold", "", "clima"),
        ("Foudre", "bold", "bolt", "clima"),
        ("Tempête", "bold", "", "clima costa"),
        ("Tonnerre", "bold", "bolt", "clima"),
        ("Loup", "bold", "jaguar", "fauna frio"),
        ("Taureau", "bold", "bull", "fauna rural"),
        ("Bastion", "steadfast", "shield_boss", "valor expansion"),
        ("Rempart", "steadfast", "shield_boss", "valor expansion"),
        ("Gardiens", "steadfast", "tower", "valor expansion"),
        ("Sentinelle", "steadfast", "tower", "valor moderna"),
        ("Enclume", "steadfast", "anvil", "oficio"),
        ("Forge", "steadfast", "anvil", "oficio"),
        ("Moulin", "steadfast", "gear", "oficio"),
        ("Acier", "steadfast", "anvil", "valor expansion"),
        ("Rail", "steadfast", "gear", "oficio urbano"),
        ("Saline", "steadfast", "", "terreno arido oficio costa"),
        ("Gel", "steadfast", "", "clima frio"),
        ("Orion", "cosmic", "constellation", "valor contemporanea"),
        ("Lyre", "cosmic", "constellation", "valor contemporanea"),
        ("Comète", "cosmic", "comet", "valor contemporanea"),
        ("Sirius", "cosmic", "constellation", "valor contemporanea"),
        ("Étoile", "cosmic", "star", "valor moderna"),
        ("Aurore", "cosmic", "sun", "valor mutualista"),
        ("Aube", "cosmic", "sun", "valor mutualista"),
        ("Lune", "cosmic", "moon", "valor contemporanea"),
        ("Monts", "nature", "summit", "terreno altura"),
        ("Roc", "nature", "summit", "terreno altura"),
        ("Vallée", "nature", "", "terreno"),
        ("Lande", "nature", "", "terreno rural"),
        ("Dune", "nature", "wave", "terreno costa arido"),
        ("Sable", "nature", "wave", "terreno costa"),
        ("Fleuve", "nature", "river", "agua"),
        ("Source", "nature", "river", "agua"),
        ("Houle", "nature", "wave", "agua costa"),
        ("Marée", "nature", "wave", "agua costa"),
        ("Vent", "nature", "", "clima"),
        ("Brume", "nature", "", "clima frio costa"),
        ("Soleil", "nature", "sun", "clima"),
        ("Chênes", "nature", "oak", "flora"),
        ("Hêtre", "nature", "oak", "flora"),
        ("Saule", "nature", "oak", "flora agua"),
        ("Pin", "nature", "pine", "flora frio"),
        ("Cèdre", "nature", "pine", "flora"),
        ("Vigne", "nature", "", "flora rural"),
    )
)

_KO_ROOTS = _curated(
    (
        ("한마음", "community", "", "valor mutualista"),
        ("고향", "community", "home_plate", "valor mutualista rural"),
        ("연대", "community", "", "valor mutualista"),
        ("동행", "community", "", "valor moderna"),
        ("청춘", "community", "", "valor moderna"),
        ("항구", "community", "bridge", "agua costa urbano"),
        ("비상", "ambition", "bird", "valor moderna"),
        ("정상", "ambition", "summit", "valor expansion"),
        ("개척", "ambition", "", "valor moderna"),
        ("개척자", "ambition", "", "valor moderna"),
        ("영광", "ambition", "crown", "valor moderna"),
        ("희망", "ambition", "", "valor mutualista"),
        ("미래", "ambition", "", "valor contemporanea"),
        ("전진", "ambition", "", "valor mutualista moderna"),
        ("자유", "ambition", "crown", "valor mutualista"),
        ("매", "ambition", "bird", "fauna"),
        ("불꽃", "bold", "flame", "valor expansion"),
        ("천둥", "bold", "bolt", "clima"),
        ("번개", "bold", "bolt", "clima"),
        ("질풍", "bold", "", "clima"),
        ("파도", "bold", "wave", "agua costa"),
        ("호랑이", "bold", "jaguar", "fauna"),
        ("늑대", "bold", "jaguar", "fauna frio"),
        ("수호", "steadfast", "shield_boss", "valor expansion"),
        ("성벽", "steadfast", "shield_boss", "valor expansion"),
        ("강철", "steadfast", "anvil", "valor expansion"),
        ("대장간", "steadfast", "anvil", "oficio"),
        ("방앗간", "steadfast", "gear", "oficio"),
        ("철도", "steadfast", "gear", "oficio urbano"),
        ("등대", "steadfast", "tower", "agua costa"),
        ("서리", "steadfast", "", "clima frio"),
        ("소금", "steadfast", "", "terreno arido costa oficio"),
        ("오리온", "cosmic", "constellation", "valor contemporanea"),
        ("북극성", "cosmic", "star", "valor contemporanea"),
        ("혜성", "cosmic", "comet", "valor contemporanea"),
        ("시리우스", "cosmic", "constellation", "valor contemporanea"),
        ("은하", "cosmic", "star", "valor contemporanea"),
        ("새벽", "cosmic", "sun", "valor mutualista"),
        ("별", "cosmic", "star", "valor moderna"),
        ("산맥", "nature", "summit", "terreno altura"),
        ("고원", "nature", "summit", "terreno altura"),
        ("언덕", "nature", "", "terreno"),
        ("큰강", "nature", "river", "agua"),
        ("물결", "nature", "wave", "agua costa"),
        ("바다", "nature", "wave", "agua costa"),
        ("모래", "nature", "wave", "terreno arido costa"),
        ("바람", "nature", "", "clima"),
        ("안개", "nature", "", "clima altura frio"),
        ("해돋이", "nature", "sun", "clima"),
        ("소나무", "nature", "pine", "flora frio"),
        ("참나무", "nature", "oak", "flora"),
        ("단풍", "nature", "rose", "flora"),
    )
)

_RU_ROOTS = _curated(
    (
        ("Единство", "community", "", "valor mutualista"),
        ("Родина", "community", "home_plate", "valor mutualista rural"),
        ("Содружество", "community", "", "valor mutualista"),
        ("Народ", "community", "home_plate", "valor mutualista"),
        ("Дружба", "community", "bridge", "valor mutualista moderna"),
        ("Согласие", "community", "bridge", "valor mutualista"),
        ("Братство", "community", "", "valor mutualista"),
        ("Юность", "community", "", "valor moderna"),
        ("Взлёт", "ambition", "bird", "valor moderna"),
        ("Вершина", "ambition", "summit", "valor expansion"),
        ("Авангард", "ambition", "", "valor moderna"),
        ("Слава", "ambition", "crown", "valor moderna"),
        ("Будущее", "ambition", "", "valor moderna"),
        ("Прогресс", "ambition", "", "valor mutualista moderna"),
        ("Свобода", "ambition", "crown", "valor mutualista"),
        ("Орёл", "ambition", "bird", "fauna altura"),
        ("Сокол", "ambition", "bird", "fauna"),
        ("Журавль", "ambition", "bird", "fauna agua"),
        ("Пламя", "bold", "flame", "valor expansion"),
        ("Гром", "bold", "bolt", "clima"),
        ("Буря", "bold", "", "clima"),
        ("Молния", "bold", "bolt", "clima"),
        ("Вихрь", "bold", "", "clima"),
        ("Гроза", "bold", "", "clima"),
        ("Искра", "bold", "flame", "valor contemporanea"),
        ("Волк", "bold", "jaguar", "fauna frio"),
        ("Медведь", "bold", "jaguar", "fauna frio"),
        ("Бастион", "steadfast", "shield_boss", "valor expansion"),
        ("Стражи", "steadfast", "tower", "valor expansion"),
        ("Сталь", "steadfast", "anvil", "valor expansion"),
        ("Кузница", "steadfast", "anvil", "oficio"),
        ("Мельница", "steadfast", "gear", "oficio"),
        ("Шахта", "steadfast", "gear", "oficio"),
        ("Порт", "steadfast", "bridge", "agua costa urbano oficio"),
        ("Мороз", "steadfast", "", "clima frio"),
        ("Соль", "steadfast", "", "terreno arido oficio"),
        ("Орион", "cosmic", "constellation", "valor contemporanea"),
        ("Полюс", "cosmic", "star", "valor contemporanea"),
        ("Комета", "cosmic", "comet", "valor contemporanea"),
        ("Сириус", "cosmic", "constellation", "valor contemporanea"),
        ("Звезда", "cosmic", "star", "valor moderna"),
        ("Метеор", "cosmic", "comet", "valor contemporanea"),
        ("Заря", "cosmic", "sun", "valor mutualista"),
        ("Рассвет", "cosmic", "sun", "valor mutualista"),
        ("Луна", "cosmic", "moon", "valor contemporanea"),
        ("Горы", "nature", "summit", "terreno altura"),
        ("Утёс", "nature", "summit", "terreno altura"),
        ("Холмы", "nature", "", "terreno"),
        ("Долина", "nature", "", "terreno"),
        ("Степь", "nature", "wheat", "terreno rural"),
        ("Тайга", "nature", "pine", "flora frio"),
        ("Река", "nature", "river", "agua"),
        ("Родник", "nature", "river", "agua"),
        ("Волна", "nature", "wave", "agua costa"),
        ("Прилив", "nature", "wave", "agua costa"),
        ("Ветер", "nature", "", "clima"),
        ("Туман", "nature", "", "clima frio altura"),
        ("Солнце", "nature", "sun", "clima"),
        ("Сосна", "nature", "pine", "flora frio"),
        ("Кедр", "nature", "pine", "flora"),
        ("Берёза", "nature", "oak", "flora frio"),
        ("Ива", "nature", "oak", "flora agua"),
    )
)

_AR_ROOTS = _curated(
    (
        ("الاتحاد", "community", "", "valor mutualista"),
        ("الوفاق", "community", "bridge", "valor mutualista"),
        ("الوحدة", "community", "", "valor mutualista"),
        ("الديار", "community", "home_plate", "valor mutualista rural"),
        ("الجذور", "community", "oak", "valor contemporanea"),
        ("الرفاق", "community", "", "valor mutualista"),
        ("الحصاد", "community", "wheat", "flora rural"),
        ("الميناء", "community", "bridge", "agua costa urbano"),
        ("النهضة", "ambition", "", "valor mutualista moderna"),
        ("القمة", "ambition", "summit", "valor expansion"),
        ("الريادة", "ambition", "", "valor moderna"),
        ("المجد", "ambition", "crown", "valor moderna"),
        ("الأمل", "ambition", "", "valor mutualista"),
        ("التقدم", "ambition", "", "valor mutualista moderna"),
        ("الحرية", "ambition", "crown", "valor mutualista"),
        ("المستقبل", "ambition", "", "valor contemporanea"),
        ("الصقر", "ambition", "bird", "fauna"),
        ("النسر", "ambition", "bird", "fauna altura"),
        ("اللهيب", "bold", "flame", "valor expansion"),
        ("الرعد", "bold", "bolt", "clima"),
        ("العاصفة", "bold", "", "clima"),
        ("البرق", "bold", "bolt", "clima"),
        ("الغزال", "bold", "", "fauna arido"),
        ("المها", "bold", "", "fauna arido"),
        ("الحصن", "steadfast", "shield_boss", "valor expansion"),
        ("الحراس", "steadfast", "tower", "valor expansion"),
        ("السنديان", "steadfast", "oak", "flora"),
        ("الحديد", "steadfast", "anvil", "oficio"),
        ("الحدادون", "steadfast", "anvil", "oficio"),
        ("الطواحين", "steadfast", "gear", "oficio"),
        ("السكة", "steadfast", "gear", "oficio urbano"),
        ("المنارة", "steadfast", "tower", "agua costa"),
        ("الملح", "steadfast", "", "terreno arido oficio"),
        ("الجبار", "cosmic", "constellation", "valor contemporanea"),
        ("القطب", "cosmic", "star", "valor contemporanea"),
        ("المذنب", "cosmic", "comet", "valor contemporanea"),
        ("الشعرى", "cosmic", "constellation", "valor contemporanea"),
        ("النجم", "cosmic", "star", "valor moderna"),
        ("القمر", "cosmic", "moon", "valor contemporanea"),
        ("الفجر", "cosmic", "sun", "valor mutualista"),
        ("الشروق", "cosmic", "sun", "valor mutualista"),
        ("الجبال", "nature", "summit", "terreno altura"),
        ("الهضبة", "nature", "summit", "terreno altura"),
        ("الوادي", "nature", "", "terreno"),
        ("السهل", "nature", "wheat", "terreno rural"),
        ("الواحة", "nature", "", "terreno arido"),
        ("الصحراء", "nature", "", "terreno arido"),
        ("الكثبان", "nature", "wave", "terreno arido costa"),
        ("الرمال", "nature", "wave", "terreno arido"),
        ("النهر", "nature", "river", "agua"),
        ("البحر", "nature", "wave", "agua costa"),
        ("الموج", "nature", "wave", "agua costa"),
        ("الريح", "nature", "", "clima"),
        ("المطر", "nature", "", "clima tropical"),
        ("الندى", "nature", "", "clima"),
        ("الشمس", "nature", "sun", "clima"),
        ("النخيل", "nature", "pine", "flora tropical arido"),
        ("الزيتون", "nature", "oak", "flora"),
    )
)

# Lingala: el inventario más corto a propósito. Se amplía con palabras
# corrientes de las que hay constancia; donde el motor no tiene certeza, no
# inventa. Es el mismo criterio que deja a un país sin gramática con su
# topónimo y nada más.
_LN_ROOTS = _curated(
    (
        ("Bomoko", "community", "", "valor mutualista"),
        ("Bondeko", "community", "bridge", "valor mutualista"),
        ("Boyokani", "community", "bridge", "valor mutualista"),
        ("Mboka", "community", "home_plate", "valor mutualista rural"),
        ("Misisa", "community", "oak", "valor contemporanea"),
        ("Baninga", "community", "", "valor mutualista"),
        ("Mosala", "community", "gear", "oficio"),
        ("Bopumbwi", "ambition", "bird", "valor moderna"),
        ("Likolo", "ambition", "summit", "valor expansion"),
        ("Bokambi", "ambition", "", "valor moderna"),
        ("Nkembo", "ambition", "crown", "valor moderna"),
        ("Elikya", "ambition", "", "valor mutualista"),
        ("Bokonzi", "ambition", "crown", "valor expansion"),
        ("Ndeke", "ambition", "bird", "fauna"),
        ("Moto", "bold", "flame", "valor expansion"),
        ("Nkake", "bold", "bolt", "clima tropical"),
        ("Mbonge", "bold", "wave", "agua costa"),
        ("Mpiko", "bold", "", "valor expansion"),
        ("Nkoi", "bold", "jaguar", "fauna tropical"),
        ("Nzoku", "steadfast", "elephant", "fauna tropical"),
        ("Ekengelo", "steadfast", "shield_boss", "valor expansion"),
        ("Babateli", "steadfast", "tower", "valor expansion"),
        ("Ebende", "steadfast", "anvil", "oficio"),
        ("Libanga", "steadfast", "", "terreno"),
        ("Molende", "steadfast", "anvil", "valor mutualista"),
        ("Bosembo", "steadfast", "", "valor mutualista"),
        ("Minzoto", "cosmic", "star", "valor contemporanea"),
        ("Monzoto", "cosmic", "star", "valor contemporanea"),
        ("Mokometi", "cosmic", "comet", "valor contemporanea"),
        ("Ntongo", "cosmic", "sun", "valor mutualista"),
        ("Butu", "cosmic", "moon", "valor contemporanea"),
        ("Lola", "cosmic", "star", "valor contemporanea"),
        ("Mwinda", "steadfast", "tower", "valor moderna urbano"),
        ("Ngomba", "nature", "summit", "terreno altura"),
        ("Ebale", "nature", "river", "agua"),
        ("Mai", "nature", "river", "agua"),
        ("Mopepe", "nature", "", "clima"),
        ("Moi", "nature", "sun", "clima"),
        ("Nzete", "nature", "oak", "flora"),
        ("Zelo", "nature", "wave", "terreno costa"),
        ("Mbisi", "nature", "wave", "agua tropical"),
        ("Mokili", "nature", "", "terreno"),
    )
)


def _curated_forms(patterns: tuple[tuple[str, str, float], ...]) -> tuple[Form, ...]:
    return tuple(Form(kind, pattern, weight=weight) for kind, pattern, weight in patterns)


#: Patronazgo en portugués: el idioma tiene repertorio de apellidos, así que la
#: veta tiene material con el que trabajar.
_PT_PATRON_FORMS: tuple[Form, ...] = (
    Form("institutional", "Clube {patron}", weight=1.1, vetas=frozenset({"patronazgo"})),
    Form("institutional", "Desportivo {patron}", weight=1.0, vetas=frozenset({"patronazgo"})),
    Form("institutional", "Clube {patron} Irmãos", weight=0.4, vetas=frozenset({"patronazgo"})),
)

_CURATED_FORMS: dict[str, tuple[Form, ...]] = {
    "pt": _curated_forms(
        (
            ("symbolic", "{noun}", 1.8),
            ("relational", "{noun} de {place}", 1.6),
            ("territorial", "{place} {noun}", 1.0),
            ("institutional", "Clube {noun}", 1.0),
            ("institutional", "Atlético {noun}", 0.6),
            ("institutional", "Associação Desportiva {noun}", 0.5),
            ("territorial", "Clube {place}", 0.7),
            ("territorial", "Atlético {place}", 0.5),
            ("territorial", "Associação Desportiva {place}", 0.4),
        )
    )
    + _PT_PATRON_FORMS,
    "ja": _curated_forms(
        (
            ("symbolic", "{noun}", 1.6),
            ("territorial", "{place}{noun}", 1.8),
            ("relational", "{place}の{noun}", 1.0),
            ("institutional", "{noun}野球倶楽部", 0.9),
            ("relational", "{noun}・{place}", 0.6),
            ("territorial", "{place}野球倶楽部", 0.7),
            ("institutional", "{place}スポーツ会", 0.4),
        )
    ),
    "de": _curated_forms(
        (
            ("symbolic", "{noun}", 1.6),
            ("territorial", "{place} {noun}", 1.8),
            ("relational", "{noun} aus {place}", 0.9),
            ("institutional", "Baseballclub {noun}", 1.0),
            ("institutional", "Sportverein {noun}", 0.6),
            ("territorial", "Baseballclub {place}", 0.7),
            ("territorial", "Sportverein {place}", 0.5),
        )
    ),
    "fr": _curated_forms(
        (
            ("symbolic", "{noun}", 1.6),
            ("relational", "{noun} de {place}", 1.7),
            ("territorial", "{place} {noun}", 1.0),
            ("institutional", "Club {noun}", 1.0),
            ("institutional", "Association sportive {noun}", 0.5),
            ("territorial", "Club de {place}", 0.7),
            ("territorial", "Association sportive de {place}", 0.4),
        )
    ),
    "ko": _curated_forms(
        (
            ("symbolic", "{noun}", 1.6),
            ("territorial", "{place} {noun}", 1.9),
            ("relational", "{place}의 {noun}", 0.9),
            ("institutional", "{noun} 야구단", 1.0),
            ("relational", "{noun}·{place}", 0.5),
            ("territorial", "{place} 야구단", 0.7),
            ("territorial", "{place} 체육회", 0.4),
        )
    ),
    "ru": _curated_forms(
        (
            ("symbolic", "{noun}", 1.7),
            ("territorial", "{place} {noun}", 1.4),
            ("relational", "{noun} из {place}", 1.0),
            ("institutional", "Бейсбольный клуб «{noun}»", 1.0),
            ("institutional", "Спортивное общество «{noun}»", 0.5),
            ("territorial", "Бейсбольный клуб «{place}»", 0.7),
            ("territorial", "Спортивное общество «{place}»", 0.4),
        )
    ),
    "ar": _curated_forms(
        (
            ("symbolic", "{noun}", 1.7),
            ("relational", "{noun} {place}", 1.4),
            ("relational", "{noun} من {place}", 0.9),
            ("institutional", "نادي {noun}", 1.0),
            ("institutional", "الجمعية الرياضية {noun}", 0.5),
            ("territorial", "نادي {place}", 0.7),
            ("territorial", "الجمعية الرياضية في {place}", 0.4),
        )
    ),
    "ln": _curated_forms(
        (
            ("symbolic", "{noun}", 1.7),
            ("relational", "{noun} ya {place}", 1.5),
            ("territorial", "{place} {noun}", 1.0),
            ("institutional", "Lisanga {noun}", 1.0),
            ("territorial", "Lisanga ya {place}", 0.7),
            ("territorial", "Lisanga ya masano {place}", 0.4),
        )
    ),
}

#: Qué sabe decir el motor en cada idioma. `und` es la salida honesta para un
#: país sin gramática curada: el topónimo verificado del gazetteer y nada más.
LEXICONS: dict[str, LocaleLexicon] = {
    "es": LocaleLexicon(
        "es", _ES_ROOTS + _ES_VALUES + _ES_TRADES, _ES_FORMS, _ES_QUALIFIERS, derives=True
    ),
    "en": LocaleLexicon(
        "en",
        _EN_ROOTS,
        _EN_FORMS,
        ("of the North", "of the Valley", "of the River"),
        derives=True,
    ),
    "pt": LocaleLexicon("pt", _PT_ROOTS, _CURATED_FORMS["pt"], ("do Norte", "do Vale")),
    "ja": LocaleLexicon("ja", _JA_ROOTS, _CURATED_FORMS["ja"]),
    "de": LocaleLexicon("de", _DE_ROOTS, _CURATED_FORMS["de"]),
    "fr": LocaleLexicon("fr", _FR_ROOTS, _CURATED_FORMS["fr"], ("du Nord", "du Val")),
    "ko": LocaleLexicon("ko", _KO_ROOTS, _CURATED_FORMS["ko"]),
    "ru": LocaleLexicon("ru", _RU_ROOTS, _CURATED_FORMS["ru"]),
    "ar": LocaleLexicon("ar", _AR_ROOTS, _CURATED_FORMS["ar"]),
    "ln": LocaleLexicon("ln", _LN_ROOTS, _CURATED_FORMS["ln"]),
    "und": LocaleLexicon("und", (), (Form("territorial", "{place}"),)),
}

#: Idioma de la marca por país. No es el idioma de los nombres de persona
#: (`lexicon.COUNTRY_LOCALE`): un club de Osaka se llama en japonés aunque el
#: motor sólo tenga antropónimos hispanos.
CLUB_LOCALE: dict[str, str] = {
    "US": "en",
    "CA": "en",
    "GB": "en",
    "AU": "en",
    "NZ": "en",
    "IE": "en",
    "ES": "es",
    "MX": "es",
    "CU": "es",
    "DO": "es",
    "PR": "es",
    "VE": "es",
    "CO": "es",
    "AR": "es",
    "CL": "es",
    "PE": "es",
    "EC": "es",
    "UY": "es",
    "PY": "es",
    "BO": "es",
    "GT": "es",
    "HN": "es",
    "SV": "es",
    "NI": "es",
    "CR": "es",
    "PA": "es",
    "BR": "pt",
    "PT": "pt",
    "JP": "ja",
    "DE": "de",
    "AT": "de",
    "LI": "de",
    "FR": "fr",
    "BE": "fr",
    "MC": "fr",
    "LU": "fr",
    "SN": "fr",
    "CI": "fr",
    "KR": "ko",
    "KP": "ko",
    "RU": "ru",
    "BY": "ru",
    "EG": "ar",
    "SA": "ar",
    "AE": "ar",
    "DZ": "ar",
    "MA": "ar",
    "TN": "ar",
    "IQ": "ar",
    "JO": "ar",
    "LB": "ar",
    "SY": "ar",
    "SD": "ar",
    "LY": "ar",
    "QA": "ar",
    "KW": "ar",
    "CD": "ln",
    "CG": "ln",
}


def lexicon_for(country_code: str) -> LocaleLexicon:
    """El idioma de la marca de un club, o `und` si el país no tiene gramática."""
    return LEXICONS.get(CLUB_LOCALE.get(country_code.upper(), "und"), LEXICONS["und"])


#: Índice de tema → motivo gráfico, para que el logo hable de lo que dice el
#: nombre incluso cuando la palabra es acuñada: «Mezquitales» empieza por el
#: tema `mezquit`, y de ahí sale su símbolo. Incluye los temas irregulares
#: declarados (`robled-`), y se consulta de más largo a más corto para que
#: «Torre» no herede el toro.
def _stems(root: Root) -> set[str]:
    key = _key(root.lemma)
    temas = {key, key[:-1] if key[-1:] in "aeiouy" else key}
    for declarado in root.forms.values():
        tema, _, _ = declarado.rpartition("|")
        if tema:
            temas.add(_key(tema))
    # Un ideograma ya es una palabra: el mínimo de tres letras sólo tiene
    # sentido en escrituras alfabéticas, donde un prefijo corto solapa.
    return {tema for tema in temas if len(tema) >= 3 or not tema.isascii()}


MOTIF_BY_STEM: tuple[tuple[str, str], ...] = tuple(
    sorted(
        {
            (tema, root.motif)
            for lexicon in LEXICONS.values()
            for root in lexicon.roots
            if root.motif
            for tema in _stems(root)
        },
        key=lambda par: (-len(par[0]), par[0]),
    )
)


def motif_for_word(word: str) -> str:
    """El motivo de la raíz con la que empieza `word`, o `""` si ninguna."""
    plain = _key(word)
    for tema, motif in MOTIF_BY_STEM:
        if plain.startswith(tema):
            return motif
    return ""
