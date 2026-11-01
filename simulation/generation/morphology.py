"""Reglas con las que se acuña una palabra nueva y filtro de lo que no vale.

El español no deja elegir el sufijo al azar, pero sí tiene reglas firmes una vez
elegido, y son éstas: `barranca` + `-ero` da **barranquero** porque la /k/ se
escribe `qu` ante *e*; `cerveza` + `-ero` da **cervecero** porque la /θ/ se
escribe `c` ante *e*; `médano` + `-ero` da **medanero** porque al añadir sufijo
el acento se desplaza y la tilde desaparece. Ninguna de esas tres palabras está
escrita en el inventario: salen de la regla.

Lo que esto compra: el espacio nominal deja de ser una lista cerrada. Y lo que
cuesta: hay que poder rechazar lo que la combinación produzca mal, así que toda
palabra acuñada pasa por `plausibility`, que la silabea, comprueba sus ataques y
codas, descarta la sílaba repetida que a veces deja el empalme («…lo-lo…») y veta
un puñado de secuencias malsonantes.

El inglés tiene aquí mucha menos morfología y mucha más composición —«Salt
Hawks», «Timber Millers»—, que es como se nombra de verdad en ese idioma.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from simulation.generation.morphemes import LocaleLexicon, Root

PROCEDURE_VERSION = "morphology/1.0.0"

_VOWELS = "aeiouáéíóúü"
_UNSTRESSED = "aeiou"
_DEACCENT = str.maketrans("áéíóú", "aeiou")

#: Género del sufijo y su alternante femenino, cuando lo tiene. `c` marca el
#: género común: una palabra que vale para los dos («el/la caminante»).
_ES_SUFFIX_TRAITS: dict[str, tuple[str, str]] = {
    "al": ("m", ""),
    "ar": ("m", ""),
    "ral": ("m", ""),
    "eral": ("m", ""),
    "eda": ("f", ""),
    "edo": ("m", ""),
    "era": ("f", ""),
    "ana": ("f", ""),
    "ada": ("f", ""),
    "ina": ("f", ""),
    "ero": ("m", "era"),
    "or": ("m", "ora"),
    "dor": ("m", "dora"),
    "ano": ("m", "ana"),
    "eño": ("m", "eña"),
    "izo": ("m", "iza"),
    "oso": ("m", "osa"),
    "ario": ("m", "aria"),
    "ante": ("c", ""),
    "ista": ("c", ""),
    "arrón": ("m", ""),
}

#: Qué clase de palabra produce cada clase de sufijo. Un agentivo o un
#: adjetival valen para las dos ranuras: el español sustantiva sin esfuerzo
#: —«los Ribereños»— y adjetiva igual de fácil —«Deportivo Cervecero»—.
_ROLES = {
    "colectivo": ("noun",),
    "agentivo": ("noun", "adj"),
    "adjetival": ("adj", "noun"),
    "aumentativo": ("noun",),
    "compuesto": ("noun",),
}

# Ataques posibles del español, incluidos los de origen náhuatl que el léxico
# mexicano necesita (`tlacuache`, `tzotzil`).
_ES_ONSETS = frozenset(
    (
        "",
        "b",
        "c",
        "ch",
        "d",
        "f",
        "g",
        "h",
        "j",
        "k",
        "l",
        "ll",
        "m",
        "n",
        "ñ",
        "p",
        "q",
        "qu",
        "r",
        "rr",
        "s",
        "t",
        "v",
        "w",
        "x",
        "y",
        "z",
        "bl",
        "br",
        "cl",
        "cr",
        "dr",
        "fl",
        "fr",
        "gl",
        "gr",
        "pl",
        "pr",
        "tr",
        "gu",
        "tl",
        "tz",
        "ks",
    )
)
_ES_CODAS = frozenset(
    (
        "",
        "n",
        "r",
        "l",
        "s",
        "d",
        "z",
        "m",
        "x",
        "c",
        "b",
        "g",
        "p",
        "y",
        "j",
    )
)
_ES_DOUBLE_CODAS = frozenset(f"{primera}s" for primera in "nbrldmgcptx")

#: Secuencias que no se publican. Combinar morfemas es combinar sonidos, y
#: alguna combinación cae en una palabra que nadie quiere en la camiseta de un
#: club. Es un filtro corto y explícito, no una lista de insultos.
_TABU = (
    "caca",
    "culo",
    "puta",
    "puto",
    "pene",
    "teta",
    "coño",
    "verga",
    "mierd",
    "pendej",
    "chingad",
    "pinche",
    "joder",
    "zorra",
    "polla",
    "maric",
    "mamad",
    "cojon",
    "cabron",
    "nalga",
    "pedo",
    "orin",
    "moco",
)


@dataclass(frozen=True)
class Lexeme:
    """Una palabra acuñada, con su rastro de formación.

    `formation` es lo que permite explicar el nombre después: «mezquite + -al».
    Sin ese rastro, el perfil de identidad tendría que inventarse el porqué.
    """

    singular: str
    plural: str
    gender: str
    role: str
    root: str
    family: str
    motif: str
    formation: str
    plausibility: float
    suffix_class: str = ""

    def surface(self, number: str) -> str:
        return self.plural if number == "pl" else self.singular


def _capitalize(word: str) -> str:
    return word[:1].upper() + word[1:] if word else word


def strip_accents(word: str) -> str:
    """Quita la tilde sin tocar la ñ ni la diéresis."""
    return word.translate(_DEACCENT)


def syllables_es(word: str) -> list[str]:
    """Silabea en español. Aproximación suficiente para validar, no para rimar.

    Reparte el grupo consonántico entre coda y ataque: un grupo inseparable
    (`tr`, `bl`, `ch`…) pasa entero al ataque siguiente.
    """
    plain = word.casefold()
    grupos: list[str] = []
    actual = ""
    for letra in plain:
        if letra in _VOWELS:
            actual += letra
            continue
        if actual and actual[-1] in _VOWELS:
            grupos.append(actual)
            actual = letra
        else:
            actual += letra
    if actual:
        grupos.append(actual)
    # Cada grupo es «ataque + vocales»; el resto de consonantes se reparte.
    partes: list[str] = []
    for grupo in grupos:
        if not partes:
            partes.append(grupo)
            continue
        consonantes = ""
        indice = 0
        while indice < len(grupo) and grupo[indice] not in _VOWELS:
            consonantes += grupo[indice]
            indice += 1
        resto = grupo[indice:]
        if not resto:
            partes[-1] += consonantes
            continue
        if len(consonantes) <= 1 or consonantes in _ES_ONSETS:
            partes.append(consonantes + resto)
        else:
            # Ataque máximo: «estrella» es es-tre-lla, no *est-re-lla. Se busca
            # el ataque más largo que el español admita, y lo que sobra es coda.
            corte = 0
            while corte < len(consonantes) and consonantes[corte:] not in _ES_ONSETS:
                corte += 1
            partes[-1] += consonantes[:corte]
            partes.append(consonantes[corte:] + resto)
    return partes


def _onset_coda(syllable: str) -> tuple[str, str]:
    ataque = ""
    indice = 0
    while indice < len(syllable) and syllable[indice] not in _VOWELS:
        ataque += syllable[indice]
        indice += 1
    coda = ""
    final = len(syllable)
    while final > indice and syllable[final - 1] not in _VOWELS:
        coda = syllable[final - 1] + coda
        final -= 1
    return ataque, coda


def plausibility(word: str, locale: str) -> float:
    """Cuánto se parece `word` a una palabra del idioma. `0.0` es rechazo.

    No mide belleza: mide que la palabra sea pronunciable en ese idioma, que no
    repita una sílaba por el empalme del sufijo y que no haya caído en una
    secuencia malsonante.
    """
    plain = word.casefold()
    if len(plain) < 3 or len(plain) > 17:
        return 0.0
    if any(sucio in strip_accents(plain) for sucio in _TABU):
        return 0.0
    if re.search(r"(.)\1\1", plain):
        return 0.0
    if locale == "en":
        if not re.fullmatch(r"[a-z'-]+", plain):
            return 0.0
        if re.search(r"[bcdfghjklmnpqrstvwxz]{4}", plain):
            return 0.0
        if re.search(r"(..)\1", plain) and len(plain) < 9:
            return 0.0
        silabas = max(1, len(re.findall(r"[aeiouy]+", plain)))
        return round(max(0.35, 1.0 - abs(silabas - 3) * 0.12), 4)
    if locale != "es":
        return 1.0
    if not re.fullmatch(r"[a-záéíóúüñ'-]+", plain):
        return 0.0
    if re.search(r"[aeiouáéíóú]{4}", plain):
        return 0.0
    silabas = syllables_es(plain)
    for indice, silaba in enumerate(silabas):
        ataque, coda = _onset_coda(silaba)
        if ataque not in _ES_ONSETS or not (coda in _ES_CODAS or coda in _ES_DOUBLE_CODAS):
            return 0.0
        # Haplología: el empalme no puede repetir la sílaba anterior.
        if indice and silaba == silabas[indice - 1]:
            return 0.0
    if not silabas:
        return 0.0
    if len(silabas) == 1:
        # «Sol» o «Maíz» son palabras; sólo son apodos más pobres que «Salineros».
        return 0.55
    # Dos a cuatro sílabas es el cuerpo cómodo de un apodo; más, se desinfla.
    return round(max(0.3, 1.0 - max(0, len(silabas) - 4) * 0.18), 4)


def suffix_es(stem: str, suffix: str, *, explicit: bool = False) -> str:
    """Aplica el sufijo con las reglas ortográficas que exige el español.

    `explicit` marca un tema irregular escrito a mano en el inventario
    (`tranvi|ario`): ahí no se toca nada, porque quien lo escribió ya resolvió
    la irregularidad. Aplicarle la caída de vocal daría *tranvaria*.
    """
    base = stem
    if explicit:
        return base + suffix
    if suffix[0] in _VOWELS:
        if base[-1] in _UNSTRESSED:
            base = base[:-1]
        if suffix[0] in "ei":
            if base.endswith("z"):
                base = base[:-1] + "c"
            elif base.endswith("c"):
                base = base[:-1] + "qu"
            elif base.endswith("gu"):
                base = base[:-2] + "gü"
            elif base.endswith("g"):
                base += "u"
    return strip_accents(base) + suffix


def plural_es(word: str) -> str:
    """Plural del español, con la tilde que se pierde o se conserva."""
    plain = word
    last = plain[-1]
    if last in "aeiou":
        return plain + "s"
    if last in "áéó":
        return plain + "s"
    if last in "íú":
        return plain + "es"
    if last == "z":
        return plain[:-1] + "ces"
    if last in "ns" and any(vocal in plain for vocal in "áéíóú"):
        # «cañón» → «cañones»: el acento sigue en su sílaba y deja de escribirse.
        return strip_accents(plain) + "es"
    if last == "s":
        return plain
    return plain + "es"


def plural_en(word: str) -> str:
    plain = word
    if plain.endswith(("s", "sh", "ch", "x", "z")):
        return plain + "es"
    if plain.endswith("y") and plain[-2:-1].lower() not in tuple("aeiou"):
        return plain[:-1] + "ies"
    if plain.endswith("f"):
        return plain[:-1] + "ves"
    return plain + "s"


def _plural(word: str, locale: str) -> str:
    if locale == "es":
        return plural_es(word)
    if locale == "en":
        return plural_en(word)
    return word


def _is_proper(root: Root, lexicon: LocaleLexicon) -> bool:
    """Un nombre propio del inventario no se deriva ni se pluraliza."""
    return lexicon.derives and root.lemma[:1].isupper()


def lexemes_for(root: Root, lexicon: LocaleLexicon) -> tuple[Lexeme, ...]:
    """Todas las palabras que esta raíz puede dar en este idioma.

    Incluye el lema y cada clase de sufijo que la raíz licencia, con sus dos
    géneros cuando el sufijo tiene alternante. Lo que no pasa el filtro de
    plausibilidad no sale.
    """
    locale = lexicon.locale
    salida: list[Lexeme] = []

    vistas: set[tuple[str, str, str]] = set()

    def añadir(
        singular: str, gender: str, role: str, formation: str, suffix_class: str, plural: str = ""
    ) -> None:
        score = plausibility(singular, locale)
        if not score or (singular, gender, role) in vistas:
            return
        vistas.add((singular, gender, role))
        salida.append(
            Lexeme(
                singular=_capitalize(singular),
                plural=_capitalize(plural or _plural(singular, locale)),
                gender=gender,
                role=role,
                root=root.key,
                family=root.family,
                motif=root.motif,
                formation=formation,
                plausibility=score,
                suffix_class=suffix_class,
            )
        )

    lemma = root.lemma
    propio = _is_proper(root, lexicon)
    if not lexicon.derives:
        # Inventario curado: la palabra se usa tal cual, sin flexión inventada.
        salida.append(
            Lexeme(
                singular=lemma,
                plural=root.plural or lemma,
                gender=root.gender,
                role="noun",
                root=root.key,
                family=root.family,
                motif=root.motif,
                formation=f"{lemma} (inventario de {locale})",
                plausibility=1.0,
                suffix_class="",
            )
        )
        return tuple(salida)

    invariable = propio or root.collective or "abstracto" in root.tags
    plural_lemma = lemma if invariable else (root.plural or _plural(lemma, locale))
    añadir(lemma, root.gender, "noun", f"{lemma} (lema)", "", plural=root.plural or plural_lemma)
    if propio:
        return tuple(salida)

    for suffix_class, roles in _ROLES.items():
        allomorph = root.allomorph(suffix_class)
        if allomorph is None:
            continue
        stem, suffix = allomorph
        if locale == "es":
            explicit = bool(root.forms[suffix_class].rpartition("|")[0])
            derived = suffix_es(stem, suffix, explicit=explicit)
            gender, feminine = _ES_SUFFIX_TRAITS.get(suffix, ("m", ""))
            traza = f"{lemma} + -{suffix}"
            for role in roles:
                añadir(derived, "c" if gender == "c" else gender, role, traza, suffix_class)
            if feminine:
                # Sólo adjetivo: el apodo de un gremio va en masculino plural.
                añadir(
                    suffix_es(stem, feminine, explicit=explicit),
                    "f",
                    "adj",
                    f"{lemma} + -{feminine}",
                    suffix_class,
                )
        else:
            # Fuera del español sólo se acuña el sustantivo: la concordancia
            # adjetival de otro idioma no está implementada y no se finge.
            derived = stem + suffix
            añadir(derived, "n", "noun", f"{lemma} + -{suffix}", suffix_class)
    return tuple(salida)


def compound_en(modifier: Root, head: Lexeme) -> Lexeme | None:
    """Compone «Salt Hawks»: el modificador del territorio y la cabeza plural.

    Es la construcción viva del béisbol en inglés, y multiplica el repertorio
    sin acuñar una sola palabra extraña: las dos piezas existen por separado.
    """
    primero = _capitalize(modifier.lemma)
    if head.plural.casefold().startswith(modifier.lemma.casefold()[:3]):
        return None
    return Lexeme(
        singular=f"{primero} {head.singular}",
        plural=f"{primero} {head.plural}",
        gender="n",
        role="noun",
        root=f"{modifier.key}+{head.root}",
        family=head.family if head.motif else modifier.family,
        motif=head.motif or modifier.motif,
        formation=f"{modifier.lemma} + {head.singular.casefold()}",
        plausibility=min(head.plausibility, plausibility(modifier.lemma, "en") or 0.5),
        suffix_class="compuesto",
    )
