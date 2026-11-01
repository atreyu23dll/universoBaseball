"""De dónde sale el nombre de un club: la veta que lo motiva.

Un nombre no es un adorno sorteado: es la huella de algo que ya le pasó al club.
Antes de acuñar una palabra, el motor decide **por qué** se va a llamar así, y
sólo puede ser por una de estas tres vetas:

- **territorio** — lo que se ve y crece donde juega. Sale de la altitud, de la
  franja climática que implica la latitud y del tamaño de la plaza: un club a
  2.400 m no comparte vocabulario con uno de la costa tropical.
- **época** — cuándo se fundó. Las sociedades de principios de siglo se
  nombraban por sus valores (Porvenir, Fraternidad, Alianza); la marca
  contemporánea prefiere una palabra sola y corta.
- **patronazgo** — quién lo sostiene. Una casa familiar o una empresa pone su
  apellido delante, y su gremio detrás.

La veta elegida **restringe el vocabulario y la gramática**: no es una etiqueta
descriptiva añadida después. De ahí sale también el relato que el perfil de
identidad guarda para poder explicar la decisión.

Honestidad sobre el clima: el motor no tiene datos de precipitación ni de
distancia a la costa. La franja árida subtropical se deduce de la latitud, que
es un patrón real pero grueso, y por eso el relato lo marca como estimación.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from simulation.generation.morphemes import Root

PROCEDURE_VERSION = "motivation/1.0.0"

VETAS = ("territorio", "epoca", "patronazgo")

#: Ejes excluyentes del hábitat. Una raíz tropical en una plaza árida no es
#: imposible —hay palmeras en un oasis—, pero no puede ser lo normal.
_AXES = (
    frozenset({"tropical", "arido", "frio"}),
    frozenset({"urbano", "rural"}),
)

_ERAS = (
    (1940, "mutualista"),
    (1970, "moderna"),
    (1995, "expansion"),
    (10_000, "contemporanea"),
)

_ERA_STORY = {
    "mutualista": (
        "cuando una sociedad deportiva se nombraba por lo que decía defender: "
        "el porvenir, la fraternidad, la alianza del barrio"
    ),
    "moderna": (
        "en los años en que el club se presentaba como institución civil: "
        "juventud, centenario, progreso"
    ),
    "expansion": (
        "en la época en que el nombre tenía que sonar en una grada: una palabra con filo"
    ),
    "contemporanea": "cuando una marca deportiva busca una palabra sola y corta",
}

#: Gobiernos que llevan un patrón detrás, y con cuánta fuerza se le ve el
#: apellido. Un colectivo vecinal no lleva ninguno.
_PATRON_PULL = {
    "family_private": 2.4,
    "business_backed": 2.5,
    "sports_company": 1.7,
    "franchise": 1.5,
    "foundation": 1.2,
    "members_assembly": 0.4,
    "collective": 0.14,
    "school_program": 0.25,
    "municipal_program": 0.1,
}

#: Cómo se nombra al patrón según lo que es. Un colectivo vecinal puede tener
#: detrás el negocio de una familia del barrio, pero no «una empresa».
_PATRON_LABEL = {
    "business_backed": "la empresa {patron} respalda al club",
    "sports_company": "la sociedad deportiva {patron} lo explota",
    "franchise": "la promotora {patron} estableció la franquicia",
    "family_private": "la familia {patron} lo sostiene",
    "foundation": "la fundación {patron} lo sostiene",
    "members_assembly": "la casa {patron} es el socio fundador",
}
_PATRON_DEFAULT = "el negocio de la familia {patron} apadrina al club"

_TYPE_PULL = {
    "private": 2.0,
    "corporate": 2.2,
    "franchise": 1.4,
    "university": 0.4,
    "municipal": 0.2,
    "community": 0.3,
}


@dataclass(frozen=True)
class NamingFacts:
    """Lo que el club ya es en el momento de ponerle nombre.

    Todo es opcional salvo la plaza: un consumidor que aún no cablee la
    geografía o el año de fundación no se queda sin nombre, se queda sin esa
    veta. Es la diferencia entre degradar y fallar.
    """

    place_name: str
    country_code: str = ""
    institutional_type: str = ""
    governance: str = ""
    foundation_year: int | None = None
    elevation_m: int | None = None
    latitude: float | None = None
    catchment_population: int | None = None
    #: Apellido del fundador o de la casa. Vacío: lo sortea el generador si el
    #: idioma de la marca tiene repertorio de apellidos.
    patron: str = ""


@dataclass(frozen=True)
class Motivation:
    """La veta elegida, lo que implica y cómo se cuenta."""

    veta: str
    habitat: frozenset[str]
    era: str
    patron: str
    story: str
    confidence: str

    def weight_for(self, root: Root) -> float:
        """Cuánto encaja una raíz con esta veta. `0.0` la deja fuera."""
        if self.veta == "territorio":
            if not root.tags & {"terreno", "flora", "fauna", "agua", "clima"}:
                return 0.0
            peso = 1.0
            for eje in _AXES:
                propias, suyas = self.habitat & eje, root.tags & eje
                if suyas and propias and not (suyas & propias):
                    return 0.12
                if suyas and suyas & propias:
                    peso += 2.0
            return peso
        if self.veta == "epoca":
            if "valor" not in root.tags:
                return 0.0
            epocas = root.tags & {era for _, era in _ERAS}
            if not epocas:
                return 0.5
            return 3.0 if self.era in epocas else 0.18
        if self.veta == "patronazgo":
            if "oficio" in root.tags:
                return 3.0
            if root.tags & {"valor", "fauna"}:
                return 0.6
            return 0.0
        return 1.0


def era_of(year: int | None) -> str:
    """La época a la que pertenece un año de fundación."""
    if year is None:
        return ""
    for limite, nombre in _ERAS:
        if year < limite:
            return nombre
    return "contemporanea"


def habitat_of(facts: NamingFacts) -> frozenset[str]:
    """Qué clase de sitio es la plaza, con los datos que el motor sí tiene."""
    tags: set[str] = set()
    if facts.elevation_m is not None:
        if facts.elevation_m >= 1800:
            tags |= {"altura", "frio"}
        elif facts.elevation_m >= 700:
            tags.add("altura")
    if facts.latitude is not None:
        grados = abs(facts.latitude)
        if grados < 23.5:
            tags.add("tropical")
        elif grados < 35.0:
            tags.add("arido")
        else:
            tags.add("frio")
    if facts.catchment_population:
        tags.add("urbano" if facts.catchment_population >= 400_000 else "rural")
    # La altitud manda sobre la latitud: una plaza tropical a 2.500 m no es
    # tropical para lo que crece en ella.
    if "altura" in tags and "frio" in tags:
        tags.discard("tropical")
    return frozenset(tags)


def _place_story(facts: NamingFacts, habitat: frozenset[str]) -> str:
    rasgos = []
    if facts.elevation_m is not None and facts.elevation_m >= 700:
        rasgos.append(f"a {facts.elevation_m} m")
    if "tropical" in habitat:
        rasgos.append("en latitud tropical")
    elif "arido" in habitat:
        rasgos.append("en la franja árida subtropical (estimada por latitud)")
    elif "frio" in habitat:
        rasgos.append("en latitud templada")
    if "urbano" in habitat:
        rasgos.append("en una plaza grande")
    elif "rural" in habitat:
        rasgos.append("en una plaza pequeña")
    return ", ".join(rasgos) or "sin datos de geografía"


def choose_motivation(
    rng: random.Random,
    facts: NamingFacts,
    *,
    surnames: tuple[str, ...] = (),
    ambition: float = 0.5,
    community_reach: float = 0.5,
) -> Motivation:
    """Elige la veta del nombre y resuelve lo que esa veta necesita saber.

    El sorteo está ponderado por lo que el club es: una empresa deportiva
    enseña a su patrón mucho más que un colectivo vecinal, y un club viejo se
    nombra por sus valores más que uno de 2019.
    """
    habitat = habitat_of(facts)
    era = era_of(facts.foundation_year)
    patron = facts.patron
    if not patron and surnames:
        patron = rng.choice(sorted(surnames))

    territorio = 1.1 + (0.9 if habitat else 0.0) + community_reach * 0.8
    # Sin año de fundación la veta sigue disponible: un club puede nombrarse por
    # lo que dice defender aunque el motor no sepa datarlo. Lo que se pierde es
    # el registro de la época, y por eso pesa menos que cualquier época sabida.
    epoca = {
        "": 0.9,
        "mutualista": 1.9,
        "moderna": 1.5,
        "expansion": 1.0,
        "contemporanea": 0.8,
    }[era] + ambition * 0.4
    patronazgo = 0.0
    if patron:
        patronazgo = _PATRON_PULL.get(facts.governance, 0.0) + _TYPE_PULL.get(
            facts.institutional_type, 0.4
        )

    opciones = (("territorio", territorio), ("epoca", epoca), ("patronazgo", patronazgo))
    total = sum(peso for _, peso in opciones)
    aguja = rng.random() * total
    veta = "territorio"
    for nombre, peso in opciones:
        aguja -= peso
        if aguja <= 0 and peso > 0:
            veta = nombre
            break

    if veta == "territorio":
        story = f"Nombre por territorio: {facts.place_name}, {_place_story(facts, habitat)}."
        confidence = "estimated" if habitat else "fictional"
    elif veta == "epoca":
        story = (
            f"Nombre por época: fundado en {facts.foundation_year}, {_ERA_STORY[era]}."
            if era
            else (
                "Nombre por los valores que el club dice defender; sin año de "
                "fundación conocido, el registro de época no se puede fijar."
            )
        )
        confidence = "fictional"
    else:
        quien = _PATRON_LABEL.get(facts.governance, _PATRON_DEFAULT).format(patron=patron)
        story = f"Nombre por patronazgo: {quien}."
        confidence = "fictional"
    return Motivation(
        veta=veta,
        habitat=habitat,
        era=era,
        patron=patron if veta == "patronazgo" else "",
        story=story,
        confidence=confidence,
    )
