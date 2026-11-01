"""Qué símbolos pertenecen a qué concepto.

Es el vínculo que faltaba. El nombre de un club ya nacía de una familia
semántica —`cosmic`, `nature`, `steadfast`…— elegida por la personalidad de
quien lo dirige, pero el logo sorteaba su motivo de una lista uniforme: un club
llamado **Nopaleras** recibía un elefante tan a menudo como un cactus, y el
cactus ni existía en el catálogo.

Con este mapa, el nombre y el símbolo hablan de lo mismo. No de forma rígida:
cada familia tiene varios motivos y siempre queda una puerta al béisbol, porque
un club de béisbol puede llevar una pelota aunque se llame Cometas.
"""

from __future__ import annotations

#: Motivos que expresan cada familia de concepto del generador de nombres.
#:
#: Un motivo puede servir a dos familias cuando de verdad expresa las dos, y
#: varios lo hacen desde la primera versión (`oak`, `summit`, `sun`, `tower`).
#: La marejada es un oleaje **bravo** y el trigal es **naturaleza**: negarles el
#: motivo que les corresponde sólo haría que su escudo saliera abstracto.
FAMILY_MOTIFS: dict[str, tuple[str, ...]] = {
    "community": ("oak", "bridge", "wheat", "home_plate", "gear"),
    "ambition": ("summit", "crown", "bird", "tower"),
    "bold": ("flame", "bolt", "bull", "jaguar", "wave"),
    "steadfast": ("shield_boss", "anvil", "oak", "gear", "elephant", "tower", "bridge"),
    "cosmic": ("star", "comet", "constellation", "moon", "sun"),
    "nature": ("cactus", "pine", "rose", "wave", "river", "summit", "sun", "oak", "wheat"),
}

#: Motivos del propio deporte. Siempre disponibles, con poco peso: identifican
#: al club como equipo de béisbol sin competir con su identidad.
SPORT_MOTIFS: tuple[str, ...] = ("ball", "crossed_bats", "home_plate", "glove")

#: Motivos que piden repetirse —tres rosas, cinco estrellas— porque su forma es
#: pequeña y en grupo construyen un emblema.
REPEATABLE: frozenset[str] = frozenset({"rose", "star", "wheat", "flame", "pine"})

#: Parámetros plausibles de cada motivo, para que dos clubes con el mismo
#: símbolo no tengan el mismo dibujo: una rosa de cinco pétalos y otra de ocho
#: son el mismo motivo y dos identidades distintas.
PARAM_CHOICES: dict[str, dict[str, tuple[float, ...]]] = {
    "star": {"points": (5, 6, 7, 8, 12), "inner": (0.38, 0.45, 0.6)},
    "rose": {"petals": (4, 5, 6, 8), "stem": (0, 1)},
    "cactus": {"arms": (1, 2, 3)},
    "pine": {"tiers": (2, 3, 4)},
    "wheat": {"grains": (4, 5, 6)},
    "summit": {"peaks": (1, 2, 3)},
    "wave": {"crests": (2, 3, 4)},
    "sun": {"rays": (6, 8, 12)},
    "gear": {"teeth": (6, 8, 10, 12)},
    "constellation": {"stars": (4, 5, 6, 7)},
    "bird": {"span": (0.7, 0.85, 1.0)},
    "jaguar": {"spots": (0, 3, 5)},
    "tower": {"levels": (2, 3, 4)},
    "bridge": {"arches": (2, 3, 4)},
    "crown": {"points": (3, 4, 5)},
    "flame": {"tongues": (1, 3)},
    "shield_boss": {"rings": (1, 2, 3)},
    "glove": {"fingers": (3, 4, 5)},
    "ball": {"seams": (1, 2)},
    "comet": {"tail": (0.3, 0.4, 0.5)},
    "crossed_bats": {"thickness": (0.08, 0.11, 0.15)},
}


def motifs_for(family: str) -> tuple[str, ...]:
    """Los motivos que puede llevar un club cuyo nombre nació de `family`."""
    return FAMILY_MOTIFS.get(family, ()) or SPORT_MOTIFS


#: Sustituto de un motivo que el renderizador no sepa trazar. Está **vacío**:
#: desde que `symbols.py` dibuja los treinta motivos del catálogo, ninguno
#: necesita pariente. La función se queda porque añadir un motivo nuevo al
#: catálogo antes que su contorno vuelve a ser posible, y entonces basta con
#: una línea aquí para que el escudo no se rompa.
DRAWABLE_FALLBACK: dict[str, str] = {}


def drawable(symbol: str) -> str:
    """El motivo que de verdad se puede dibujar para `symbol`."""
    return DRAWABLE_FALLBACK.get(symbol, symbol)


def coherent(symbol: str, family: str) -> bool:
    """Dice si un símbolo pertenece al mundo del que habla el nombre."""
    return symbol == "abstract" or symbol in motifs_for(family) or symbol in SPORT_MOTIFS


def symbol_for_concept(concept: str, family: str) -> str:
    """Sólo interpreta conceptos del nombre, nunca supuesta fauna del lugar.

    Primero pregunta al inventario de morfemas, que declara el motivo de cada
    raíz y por eso acierta con una palabra acuñada («Nopalera» → cactus).
    Después recurre al reconocimiento por tema, y **siempre** comprueba que el
    símbolo pertenezca a la familia del nombre: «Caminante del Río» no puede
    llevar un río sólo porque el modificador lo mencione, porque el nombre
    habla de comunidad y el río no es un motivo de comunidad.
    """
    import unicodedata

    from simulation.generation.morphemes import motif_for_word

    normalized = "".join(
        c for c in unicodedata.normalize("NFKD", concept.casefold()) if not unicodedata.combining(c)
    )
    cabeza = normalized.split()[0] if normalized.split() else ""
    declarado = drawable(motif_for_word(cabeza))
    if declarado:
        return declarado if coherent(declarado, family) else "abstract"
    families = (
        ("pine", ("pinar", "pino", "pine")),
        ("cactus", ("cactus", "nopal")),
        ("bridge", ("puente", "bridge", "pont")),
        ("wheat", ("trigo", "espiga", "wheat")),
        ("bull", ("toro", "bull")),
        ("bird", ("aguila", "halcon", "eagle", "falcon")),
        ("anvil", ("yunque", "anvil", "hierro", "iron", "eisen", "acier")),
        ("gear", ("engran", "gear")),
        ("moon", ("luna", "moon", "lune")),
        ("constellation", ("orion", "lira", "lyre", "auriga", "sirius", "polaris", "polarstern")),
        ("oak", ("roble", "carvalho", "chene", "oak", "raic", "raiz", "encin")),
        ("tower", ("guard", "sentinel", "centinela", "torre", "fort", "bastion")),
        ("sun", ("soleil", "sonne", "sol", "sun", "朝日", "해돋이")),
        ("river", ("rio", "river", "fleuve", "strom", "ebale", "大河", "큰강")),
        ("bolt", ("rayo", "raio", "blitz", "foudre", "lightning", "雷鳴", "천둥")),
        ("rose", ("rosa", "rose", "rosal", "roseda")),
        ("elephant", ("elefant", "elephant")),
        (
            "summit",
            (
                "sierra",
                "cumbre",
                "cume",
                "serra",
                "sommet",
                "gipfel",
                "monts",
                "mountain",
                "summit",
            ),
        ),
        ("flame", ("fuego", "fogo", "flam", "llama", "烈火", "불꽃")),
        ("comet", ("cometa", "comet", "komet", "彗星", "혜성")),
    )
    for symbol, roots in families:
        if any(word.startswith(root) for word in normalized.split() for root in roots):
            elegido = drawable(symbol)
            return elegido if coherent(elegido, family) else "abstract"
    # Una marca abstracta expresa valores sin afirmar que represente un objeto.
    return "abstract"
