"""Generación de nombres de clubes y personas, determinista y sin repetir.

El nombre de un club **no se saca de una lista**. Se acuña: una veta lo motiva
(`motivation`), una raíz del inventario lo siembra (`morphemes`), las reglas del
idioma lo forman (`morphology`) y una plantilla gramatical lo presenta. De
«salina» salen Salineros, Salinera, Salinas y Unión Salinera; de «mezquite»,
Mezquital y Mezquitales; y ninguna de esas palabras está escrita en el motor.

Lo que esto arregla, medido antes de tocarlo: con el vocabulario anterior —24
palabras acabadas por idioma— 96 clubes repetían «Viento» siete veces y «Sol»
cuatro, y los nombres sólo se distinguían por el prefijo («Club Viento»,
«Deportivo Viento», «Viento del Norte»), que para una persona es la misma marca.
Ahora el registro del universo presiona la **raíz** y la **plantilla**, no sólo
la cadena final, así que dos clubes de la misma liga no pueden sonar a lo mismo
mientras quede inventario.

El coste aceptado: generar un nombre ya no es sortear un elemento. Se eligen la
veta y varias raíces semilla, se acuñan todas sus palabras, se cruzan con las
plantillas que esa veta y esa época habilitan, se descarta lo que no pasa el
filtro fonotáctico y se puntúa lo que queda. Son unas decenas de microsegundos
por club, y a cambio el nombre se puede explicar.
"""

from __future__ import annotations

import random
import re
import unicodedata
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from simulation.generation.lexicon import (
    CLUB_PREFIXES,
    CLUB_SUFFIX_INSTITUTIONAL,
    COUNTRY_LOCALE,
    FOUNDER_SURNAMES,
    NAME_POOLS,
    NICKNAMES_CIVIC,
    NICKNAMES_FAUNA,
    NICKNAMES_GEO,
    NICKNAMES_TRADE,
)
from simulation.generation.morphemes import (
    Form,
    LocaleLexicon,
    Root,
    lexicon_for,
    motif_for_word,
)
from simulation.generation.morphology import Lexeme, compound_en, lexemes_for
from simulation.generation.motivation import (
    Motivation,
    NamingFacts,
    choose_motivation,
)
from simulation.generation.organization import OrganizationProfile

PROCEDURE_VERSION = "naming/5.0.0"

#: Cuántas candidatas se construyen antes de elegir. El nombre de un club se
#: decide una vez en su vida: vale la pena mirar unas decenas de opciones.
CANDIDATE_TARGET = 48

#: Cuántas raíces semilla recibe un club. Más de una para que la elección final
#: pueda huir de la raíz que ya usó el vecino; no tantas que la veta deje de
#: significar algo.
SEED_ROOTS = 6


def consume_legacy_club_name_entropy(
    rng: random.Random, registry: NameRegistry, place_name: str, institutional_type: str
) -> None:
    """Conserva el cauce RNG histórico para no cambiar economía ni recintos.

    Se podrá retirar al crear una nueva versión incompatible de simulación.
    """
    nicknames = _NICK_BY_TYPE.get(institutional_type, NICKNAMES_FAUNA)
    options = [name for name in nicknames if registry.is_free(f"{name}::{place_name}")]
    nickname = rng.choice(options or nicknames)
    registry.claim(f"{nickname}::{place_name}")
    shape = rng.random()
    if 0.45 <= shape < 0.75:
        rng.choice(CLUB_PREFIXES)
    elif shape >= 0.75:
        suffixes = CLUB_SUFFIX_INSTITUTIONAL.get(institutional_type) or []
        if suffixes and rng.random() < 0.6:
            rng.choice(suffixes)


_NICK_BY_TYPE = {
    "community": NICKNAMES_FAUNA + NICKNAMES_CIVIC,
    "corporate": NICKNAMES_TRADE + NICKNAMES_FAUNA,
    "university": NICKNAMES_FAUNA + NICKNAMES_CIVIC,
    "municipal": NICKNAMES_GEO + NICKNAMES_CIVIC,
    "private": NICKNAMES_FAUNA + NICKNAMES_GEO,
    "franchise": NICKNAMES_FAUNA + NICKNAMES_GEO + NICKNAMES_TRADE,
}


class NameRegistry:
    """Evita colisiones dentro de un universo.

    Reparte sin repetir mientras queden opciones; si el pool se agota añade un
    discriminante, en vez de fallar o de entregar dos clubes idénticos.

    Además de las cadenas ya entregadas lleva la cuenta de las **raíces** y de
    las **plantillas** gastadas. Es lo que faltaba: comparar nombres completos
    deja pasar «Viento», «Club Viento» y «Viento del Norte» como tres marcas,
    cuando son una. La presión no prohíbe repetir una raíz —un universo grande
    agota el inventario—, la encarece.
    """

    def __init__(self) -> None:
        self._used: set[str] = set()
        self._normalized: dict[str, str] = {}
        self._roots: Counter[str] = Counter()
        self._patterns: Counter[str] = Counter()
        self._by_prefix: dict[str, set[str]] = {}

    def _register(self, candidate: str, normalized: str) -> None:
        self._used.add(candidate)
        self._normalized[normalized] = candidate
        for prefijo in _prefixes(normalized):
            self._by_prefix.setdefault(prefijo, set()).add(normalized)

    def claim(self, candidate: str) -> str:
        normalized = normalize_club_name(candidate)
        if candidate not in self._used and normalized not in self._normalized:
            self._register(candidate, normalized)
            return candidate
        suffix = 2
        while (
            f"{candidate} {suffix}" in self._used
            or normalize_club_name(f"{candidate} {suffix}") in self._normalized
        ):
            suffix += 1
        taken = f"{candidate} {suffix}"
        self._register(taken, normalize_club_name(taken))
        return taken

    def is_free(self, candidate: str) -> bool:
        return (
            candidate not in self._used and normalize_club_name(candidate) not in self._normalized
        )

    def is_distinct(self, candidate: str, threshold: float = 0.84) -> bool:
        """Dice si una candidata no se confunde con otra ya asignada.

        La igualdad exacta no basta: «Unión Chihuahua» y «Union de
        Chihuahua» son la misma marca a ojos de una persona aunque difieran en
        acento y conector. La comparación combina secuencia y tokens; no exige
        una dependencia de similitud difusa para un problema pequeño.
        """
        normalized = normalize_club_name(candidate)
        vecinas: set[str] = set()
        for prefijo in _prefixes(normalized):
            vecinas |= self._by_prefix.get(prefijo, frozenset())
        # Dos marcas que no comparten ni el arranque de una palabra no se
        # confunden: comparar contra el universo entero era cuadrático.
        return all(club_name_similarity(normalized, other) < threshold for other in vecinas)

    def claim_identity(self, root: str, pattern: str) -> None:
        """Apunta la raíz y la plantilla que acaba de gastar un club."""
        for parte in root.split("+"):
            if parte:
                self._roots[parte] += 1
        self._patterns[pattern] += 1

    def root_pressure(self, root: str) -> float:
        """Cuánto se ha usado ya esta raíz en el universo, de 0 a 1."""
        usos = max((self._roots[parte] for parte in root.split("+") if parte), default=0)
        return min(1.0, usos * 0.72)

    def pattern_pressure(self, pattern: str) -> float:
        """Cuánto se ha usado ya esta plantilla: evita la liga de 24 «Club X»."""
        return min(1.0, self._patterns[pattern] * 0.34)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._used)


def _prefixes(normalized: str) -> set[str]:
    """Arranque de cada palabra: la clave con la que se buscan parecidos."""
    return {palabra[:4] for palabra in normalized.split()}


def normalize_club_name(value: str) -> str:
    """Forma comparable: minúsculas, sin diacríticos ni puntuación."""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    plain = "".join(character for character in decomposed if not unicodedata.combining(character))
    return " ".join(re.findall(r"[^\W_]+", plain, flags=re.UNICODE))


def club_name_similarity(left: str, right: str) -> float:
    """Similitud conservadora entre dos denominaciones, entre 0 y 1."""
    a, b = normalize_club_name(left), normalize_club_name(right)
    if not a or not b:
        return 0.0
    # Un prefijo administrativo no convierte «Lira» y «Club Lira» en dos
    # identidades distintas. No se eliminan palabras del interior del nombre.
    prefix = (
        r"^(?:(?:asociacion deportiva|sociedad deportiva|club social y deportivo|"
        r"deportivo|desportivo|atletico|fundacion|club|clube|baseballclub) )+"
    )
    core_a, core_b = re.sub(prefix, "", a), re.sub(prefix, "", b)
    if core_a == core_b:
        return 1.0
    sequence = SequenceMatcher(None, a, b).ratio()
    tokens_a, tokens_b = set(a.split()), set(b.split())
    token_score = len(tokens_a & tokens_b) / max(1, len(tokens_a | tokens_b))
    containment = min(len(tokens_a), len(tokens_b)) / max(len(tokens_a), len(tokens_b))
    if tokens_a <= tokens_b or tokens_b <= tokens_a:
        token_score = max(token_score, containment * 0.9)
    return max(sequence, token_score)


_IGNORED_IN_INITIALS = frozenset(
    (
        "club",
        "clube",
        "baseballclub",
        "asociación",
        "associação",
        "association",
        "sociedad",
        "sportverein",
        "deportivo",
        "desportivo",
        "atlético",
        "atletico",
        "fundación",
        "social",
        "deportiva",
        "desportiva",
        "sportive",
        "athletic",
        "baseball",
        "casa",
        "hermanos",
        "irmãos",
        "sons",
        "y",
        "e",
        "la",
        "el",
        "de",
        "del",
        "do",
        "da",
        "of",
        "the",
        "ya",
        "aus",
        "из",
        "من",
        "野球倶楽部",
    )
)


def _initials(value: str, maximum: int = 4) -> str:
    words = [
        word
        for word in re.findall(r"[^\W_]+", value, flags=re.UNICODE)
        if word.casefold() not in _IGNORED_IN_INITIALS
    ]
    initials = "".join(word[0] for word in words[:maximum])
    if len(initials) < 2:
        # «Deportivo Iglesias» da «I», que no es un monograma: se toman dos
        # letras de la palabra con contenido.
        unica = words[0] if words else value
        initials = unica[:2]
    return initials.upper() or value[:2].upper()


@dataclass(frozen=True)
class NameCandidate:
    """Una denominación posible, con todo lo que hizo falta para acuñarla."""

    official: str
    short: str
    nickname: str
    family: str
    grammar: str
    concept: str
    score: float
    rationale: str
    root: str = ""
    pattern: str = ""
    veta: str = ""
    formation: str = ""
    motif: str = ""


@dataclass(frozen=True)
class ClubName:
    """La identidad verbal de un club, con la familia que la engendró.

    `family` no es decoración: es el campo semántico del concepto —`cosmic`,
    `nature`, `steadfast`…— y lo necesita el logo para que el símbolo hable de
    lo mismo que el nombre. Sin él, un club llamado Nopaleras llevaba un
    elefante tan a menudo como un cactus.

    `motivation`, `story` y `formation` son la cadena de custodia del nombre:
    por qué se llama así, de qué hecho del club salió y con qué morfema se
    acuñó la palabra.
    """

    full: str
    nickname: str
    short: str
    family: str
    initials: str = ""
    sporting_demonym: str | None = None
    grammar: str = "territorial"
    concept: str = ""
    rationale: str = ""
    candidates_considered: int = 1
    root: str = ""
    motivation: str = ""
    story: str = ""
    formation: str = ""
    motif: str = ""

    # Compatibilidad deliberada: desde la primera versión, consumidores y
    # pruebas desempaquetan cuatro valores. Los campos nuevos enriquecen el
    # artefacto sin convertir una mejora de identidad en una rotura de API.
    def __iter__(self) -> Iterator[str]:
        yield self.full
        yield self.nickname
        yield self.short
        yield self.family

    def __getitem__(self, index: int) -> str:
        return (self.full, self.nickname, self.short, self.family)[index]

    def __len__(self) -> int:
        return 4


def _family_weights(organization: OrganizationProfile | None) -> dict[str, float]:
    """Cuánto tira la personalidad institucional de cada campo semántico."""
    if organization is None:
        return dict.fromkeys(
            ("community", "ambition", "bold", "steadfast", "cosmic", "nature"), 1.0
        )
    return {
        "community": 0.4 + organization.community_reach * 2.2,
        "ambition": 0.3 + organization.ambition * 2.3,
        "bold": 0.25 + organization.risk_tolerance * 2.1,
        "steadfast": 0.35 + (1.0 - organization.risk_tolerance) * 1.8,
        "cosmic": 0.55 + organization.ambition,
        "nature": 0.8 + (1.0 - organization.ambition) * 1.6,
    }


def _pick[T](rng: random.Random, pairs: Sequence[tuple[T, float]]) -> T:
    """Sorteo ponderado y reproducible sobre `(valor, peso)`."""
    total = sum(peso for _, peso in pairs)
    aguja = rng.random() * total
    for valor, peso in pairs:
        aguja -= peso
        if aguja <= 0:
            return valor
    return pairs[-1][0]


def _seed_roots(
    rng: random.Random,
    lexicon: LocaleLexicon,
    motivation: Motivation,
    families: dict[str, float],
    count: int,
) -> list[tuple[Root, float]]:
    """Las raíces que la veta pone sobre la mesa, con su ajuste."""
    pesos = [
        (root, motivation.weight_for(root), families.get(root.family, 1.0))
        for root in lexicon.roots
    ]
    viables = [(root, fit * familia, fit) for root, fit, familia in pesos if fit > 0]
    if not viables:
        viables = [(root, families.get(root.family, 1.0), 1.0) for root in lexicon.roots]
    elegidas: list[tuple[Root, float]] = []
    disponibles = [(root, peso, fit) for root, peso, fit in viables]
    for _ in range(min(count, len(disponibles))):
        indices = [(indice, peso) for indice, (_, peso, _) in enumerate(disponibles)]
        indice = int(_pick(rng, indices))  # type: ignore[arg-type]
        root, _, fit = disponibles.pop(indice)
        elegidas.append((root, fit))
    return elegidas


def _usable_forms(lexicon: LocaleLexicon, motivation: Motivation) -> list[tuple[Form, float]]:
    """Las plantillas que esta veta y esta época habilitan."""
    salida: list[tuple[Form, float]] = []
    for form in lexicon.forms:
        if form.vetas and motivation.veta not in form.vetas:
            continue
        if "{patron}" in form.pattern and not motivation.patron:
            continue
        peso = form.weight
        if form.eras:
            if motivation.era and motivation.era not in form.eras:
                continue
            if not motivation.era:
                peso *= 0.6
        salida.append((form, peso))
    return salida


def _slot_of(pattern: str) -> str:
    for slot in ("nouns", "noun", "adj_m", "adj_f"):
        if "{" + slot + "}" in pattern:
            return slot
    return ""


def _fits(lexeme: Lexeme, slot: str) -> bool:
    if slot in ("noun", "nouns"):
        return lexeme.role == "noun"
    if slot == "adj_m":
        return lexeme.role == "adj" and lexeme.gender in ("m", "n", "c")
    if slot == "adj_f":
        return lexeme.role == "adj" and lexeme.gender in ("f", "n", "c")
    return False


def _lexeme_pool(lexicon: LocaleLexicon, root: Root, motivation: Motivation) -> tuple[Lexeme, ...]:
    """Las palabras de una raíz, más los compuestos que el inglés permite."""
    palabras = list(lexemes_for(root, lexicon))
    if lexicon.locale != "en" or not palabras:
        return tuple(palabras)
    if "cabeza" in root.tags:
        modificadores = [
            otra
            for otra in lexicon.roots
            if "modificador" in otra.tags and motivation.weight_for(otra) > 0.5
        ]
        for otra in sorted(modificadores, key=lambda r: r.key)[:24]:
            compuesto = compound_en(otra, palabras[0])
            if compuesto:
                palabras.append(compuesto)
    return tuple(palabras)


def _lexeme_weight(lexeme: Lexeme, root: Root) -> float:
    """Pesa la palabra dentro de su raíz: lo acuñado antes que el lema."""
    peso = lexeme.plausibility
    if lexeme.suffix_class:
        peso *= 1.7
    elif "oficio" in root.tags:
        # «Cerveza» o «Azúcar» son la materia, no el gremio: sólo entran si la
        # raíz no licencia ninguna derivación.
        peso *= 0.08
    return peso


def _nouns_of(palabras: tuple[Lexeme, ...]) -> list[Lexeme]:
    """Los sustantivos de una raíz, lo derivado primero."""
    return sorted(
        (palabra for palabra in palabras if palabra.role == "noun"),
        key=lambda palabra: (palabra.suffix_class == "", -palabra.plausibility, palabra.singular),
    )


def _nickname_lexeme(sustantivos: list[Lexeme], elegido: Lexeme) -> Lexeme:
    """Cómo corea la grada a un club que se presenta con un adjetivo.

    «Deportivo Salinero» son los Salineros: el apodo es el sustantivo de la
    misma derivación, no el lema de la raíz.
    """
    if elegido.role == "noun":
        return elegido
    mismos = [palabra for palabra in sustantivos if palabra.suffix_class == elegido.suffix_class]
    return (mismos or sustantivos)[0]


def _redundant(qualifier: str, surface: str) -> bool:
    """«Arroyos del Río» dice dos veces lo mismo: el modificador no aporta."""
    nucleo = normalize_club_name(qualifier).split()[-1:]
    cabeza = normalize_club_name(surface).split()[:1]
    if not nucleo or not cabeza:
        return True
    if cabeza[0].startswith(nucleo[0][:4]) or nucleo[0].startswith(cabeza[0][:4]):
        return True
    motivo = motif_for_word(nucleo[0])
    return bool(motivo) and motivo == motif_for_word(cabeza[0])


def _short_name(official: str, concept: str, place_name: str) -> str:
    short = _SHORT_STRIP.sub("", official)
    short = " ".join(short.split())
    if short and len(short) <= 30:
        return short
    return concept if concept and len(concept) <= 30 else place_name[:30]


_SHORT_STRIP = re.compile(
    r"\b(?:Club Social y Deportivo|Asociación Deportiva|Associação Desportiva"
    r"|Sociedad Deportiva|Association sportive|Athletic Association|Baseball Club"
    r"|Athletic Club|Baseballclub|Sportverein|Deportivo|Desportivo|Atlético|Fundación"
    r"|Clube|Club|de|do|da|del)\b",
    re.IGNORECASE,
)


def _naturalness(official: str, locale: str, place_name: str) -> float:
    """Penaliza lo que un hablante leería como error, no lo que es raro."""
    score = 1.0
    length = len(official)
    if length < 4:
        score -= 0.5
    if length > 58:
        score -= min(0.6, (length - 58) / 50)
    normalized = normalize_club_name(official)
    palabras = normalized.split()
    if len(palabras) != len(set(palabras)):
        score -= 0.45
    if any(len(palabra) > 22 for palabra in palabras):
        score -= 0.2
    if locale == "und" and official != place_name:
        score -= 1.0
    return max(0.0, score)


def _toponym_only(place_name: str) -> list[NameCandidate]:
    """La salida honesta de un país sin gramática curada: su topónimo."""
    return [
        NameCandidate(
            official=place_name,
            short=place_name[:30],
            # Compatibilidad: fuera de una gramática curada el topónimo ocupa
            # también el campo histórico `nickname`; no se presenta como
            # mascota en el perfil (`grammar=territorial`).
            nickname=place_name,
            family="community",
            grammar="territorial",
            concept=place_name,
            score=1.0,
            rationale=(
                "Sólo se usa el topónimo del gazetteer: no hay una gramática "
                "local curada y el motor no inventa vocabulario cultural."
            ),
            root="",
            pattern="{place}",
            veta="territorio",
            formation="topónimo verificado",
        )
    ]


def generate_club_name_candidates(
    rng: random.Random,
    place_name: str,
    institutional_type: str,
    *,
    country_code: str = "",
    organization: OrganizationProfile | None = None,
    facts: NamingFacts | None = None,
    count: int = CANDIDATE_TARGET,
) -> list[NameCandidate]:
    """Acuña candidatas: veta, raíz, morfología y plantilla, en ese orden.

    Cada candidata conserva la veta, la raíz y el rastro morfológico que la
    produjeron, para que el perfil institucional pueda explicar la decisión
    después y para que el registro del universo pueda penalizar la raíz.
    """
    lexicon = lexicon_for(country_code)
    if not lexicon.roots:
        return _toponym_only(place_name)

    hechos = facts or NamingFacts(
        place_name=place_name,
        country_code=country_code,
        institutional_type=institutional_type,
        governance=str(organization.governance) if organization else "",
    )
    motivation = choose_motivation(
        rng,
        hechos,
        surnames=tuple(FOUNDER_SURNAMES.get(lexicon.locale, ())),
        ambition=organization.ambition if organization else 0.5,
        community_reach=organization.community_reach if organization else 0.5,
    )
    families = _family_weights(organization)
    semillas = _seed_roots(rng, lexicon, motivation, families, SEED_ROOTS)
    formas = _usable_forms(lexicon, motivation)
    if not semillas or not formas:
        return _toponym_only(place_name)
    palabras = {root.key: _lexeme_pool(lexicon, root, motivation) for root, _ in semillas}
    familia_max = max(families.values())
    peso_max = max(peso for _, peso in formas)

    candidatas: dict[str, NameCandidate] = {}
    for _ in range(max(8, count)):
        root, fit = _pick(rng, [(semilla, peso) for semilla in semillas for peso in (semilla[1],)])
        # Un bicho se corea en plural: «Coyotes», no «Club Coyote». La
        # preferencia es de la raíz, así que los pesos se ajustan por intento.
        form = _pick(
            rng,
            [
                (
                    forma,
                    peso
                    * (0.3 if "fauna" in root.tags and _slot_of(forma.pattern) == "noun" else 1.0),
                )
                for forma, peso in formas
            ],
        )
        slot = _slot_of(form.pattern)
        disponibles = [palabra for palabra in palabras[root.key] if _fits(palabra, slot)]
        if slot and not disponibles:
            continue
        sustantivos = _nouns_of(palabras[root.key])
        if not sustantivos:
            continue
        lexema = (
            _pick(rng, [(palabra, _lexeme_weight(palabra, root)) for palabra in disponibles])
            if disponibles
            else sustantivos[0]
        )
        superficie = lexema.surface("pl" if slot == "nouns" else "sg")
        if (
            lexicon.qualifiers
            and slot in ("noun", "nouns")
            and "{place}" not in form.pattern
            and rng.random() < 0.14
        ):
            modificador = rng.choice(sorted(lexicon.qualifiers))
            if not _redundant(modificador, superficie):
                superficie = f"{superficie} {modificador}"
        official = " ".join(
            form.pattern.format(
                noun=superficie,
                nouns=superficie,
                adj_m=superficie,
                adj_f=superficie,
                place=place_name,
                patron=motivation.patron,
            ).split()
        )
        natural = _naturalness(official, lexicon.locale, place_name)
        if not natural:
            continue
        apodo_lexema = _nickname_lexeme(sustantivos, lexema)
        apodo = apodo_lexema.plural if form.kind != "territorial" else ""
        concepto = (
            superficie
            if slot
            else (motivation.patron if "{patron}" in form.pattern else sustantivos[0].singular)
        )
        score = (
            natural * 0.9
            + lexema.plausibility * 0.5
            + 0.30 * (families.get(root.family, 1.0) / familia_max)
            + 0.22 * min(1.0, fit / 3.0)
            + 0.18 * (next(peso for forma, peso in formas if forma is form) / peso_max)
            + rng.random() * 0.18
        )
        candidata = NameCandidate(
            official=official,
            short=_short_name(official, concepto, place_name),
            nickname=apodo,
            family=root.family,
            grammar=form.kind,
            concept=concepto,
            score=round(score, 4),
            rationale=(
                f"{motivation.story} Palabra acuñada: {lexema.formation}; "
                f"gramática {form.kind} en {lexicon.locale} «{form.pattern}»."
            ),
            root=lexema.root,
            pattern=form.pattern,
            veta=motivation.veta,
            formation=lexema.formation,
            motif=lexema.motif,
        )
        clave = normalize_club_name(official)
        if clave not in candidatas or score > candidatas[clave].score:
            candidatas[clave] = candidata
    if not candidatas:
        return _toponym_only(place_name)
    return sorted(candidatas.values(), key=lambda c: (-c.score, c.official))


def club_name(
    rng: random.Random,
    registry: NameRegistry,
    place_name: str,
    institutional_type: str,
    country_code: str = "",
    organization: OrganizationProfile | None = None,
    scope_level: str | None = None,
    facts: NamingFacts | None = None,
) -> ClubName:
    """Genera, evalúa y reserva una identidad verbal reproducible.

    De las candidatas acuñadas se elige la mejor que no se confunda con otra
    marca del universo, descontando lo que ya se gastó: la raíz y la plantilla
    que otro club de la misma liga ya usó valen menos. Si el espacio local se
    agota, el registro añade un discriminante; nunca se entrega un duplicado.
    """
    candidates = generate_club_name_candidates(
        rng,
        place_name,
        institutional_type,
        country_code=country_code,
        organization=organization,
        facts=facts,
    )
    ordenadas = sorted(
        candidates,
        key=lambda candidate: (
            -(
                candidate.score
                - 1.25 * registry.root_pressure(candidate.root)
                - 0.45 * registry.pattern_pressure(candidate.pattern)
            ),
            candidate.official,
        ),
    )
    # Elegir la intención una vez por club: puntuar decenas de candidatas no
    # debe convertir una pequeña ventaja del topónimo en decenas de
    # oportunidades de ganar.
    territorial_chance = 0.12 if scope_level == "municipal" else 0.28
    use_place = rng.random() < territorial_chance
    place = normalize_club_name(place_name)

    def menciona(candidate: NameCandidate) -> bool:
        return place in normalize_club_name(candidate.official)

    selected = ordenadas[0]
    for exigir_intencion, exigir_distincion in ((1, 1), (0, 1), (1, 0)):
        elegida = next(
            (
                candidate
                for candidate in ordenadas
                if (not exigir_intencion or menciona(candidate) == use_place)
                and (not exigir_distincion or registry.is_distinct(candidate.official))
            ),
            None,
        )
        if elegida is not None:
            selected = elegida
            break
    official = registry.claim(selected.official)
    registry.claim_identity(selected.root, selected.pattern)
    short = (
        selected.short
        if official == selected.official
        else _short_name(official, selected.concept, place_name)
    )
    return ClubName(
        full=official,
        nickname=selected.nickname,
        short=short,
        family=selected.family,
        initials=_initials(short or official),
        sporting_demonym=None,
        grammar=selected.grammar,
        concept=selected.concept,
        rationale=(
            f"{selected.rationale} Puntuación {selected.score:.2f}; "
            f"seleccionada entre {len(candidates)} candidatas acuñadas. "
            f"Ámbito {scope_level or 'no especificado'}: la sede es opcional en la marca."
        ),
        candidates_considered=len(candidates),
        root=selected.root,
        motivation=selected.veta,
        story=selected.rationale.split(" Palabra acuñada:")[0],
        formation=selected.formation,
        motif=selected.motif,
    )


def person_name(rng: random.Random, registry: NameRegistry, country_code: str) -> tuple[str, str]:
    """Devuelve (nombre, apellidos). Dos apellidos en locales hispanos."""
    locale = COUNTRY_LOCALE.get(country_code, "es")
    given_pool, surname_pool = NAME_POOLS[locale]

    for _ in range(40):
        given = rng.choice(given_pool)
        if locale == "es" and rng.random() < 0.18:
            given = f"{given} {rng.choice(given_pool)}"
        first_surname = rng.choice(surname_pool)
        second_surname = rng.choice(surname_pool)
        while second_surname == first_surname:
            second_surname = rng.choice(surname_pool)
        surnames = f"{first_surname} {second_surname}"
        if registry.is_free(f"{given} {surnames}"):
            registry.claim(f"{given} {surnames}")
            return given, surnames

    given = rng.choice(given_pool)
    surnames = f"{rng.choice(surname_pool)} {rng.choice(surname_pool)}"
    registry.claim(f"{given} {surnames}")
    return given, surnames


def venue_name(rng: random.Random, registry: NameRegistry, place_name: str, nickname: str) -> str:
    patterns = [
        f"Parque {nickname}",
        f"Campo Municipal de {place_name}",
        f"Estadio {nickname} de {place_name}",
        f"Parque de Pelota {place_name}",
        f"Diamante {nickname}",
    ]
    return registry.claim(rng.choice(patterns))
