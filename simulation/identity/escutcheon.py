"""La silueta del escudo, construida y no elegida de un catálogo.

Antes había **una** ruta de escudo escrita a mano, y todos los clubes la
llevaban igual. Eso es lo que hace que una tanda de escudos parezca una
plantilla: por mucho que cambien el color y el símbolo, el contorno es lo
primero que ve el ojo y era idéntico.

Aquí la silueta se construye por mitades: se describe el flanco derecho con
parámetros de blasón —anchura de hombros, caída del jefe, curvatura del flanco,
forma de la punta— y se refleja. Los parámetros no son independientes: van por
**familias** —inglés de punta, francés moderno, ibérico redondo, oval italiano,
de torneo con muesca, barroco de cintura, estandarte—, porque sortear cada
número por su cuenta produce calderos y bombillas, no escudos. Dentro de la
familia hay azar de sobra para que dos clubes no salgan calcados.

Tres reglas que no se rompen:

- **La silueta es una sola curva cerrada**, y el campo, la bordura interior y
  la máscara de las particiones usan la misma: si el recorte no coincide con el
  borde, se ve una pestaña de color.
- **La muesca de lanza es asimétrica**, como en el escudo de torneo real: se
  abre después de reflejar, en un solo flanco.
- **Todo cabe en el lienzo.** La caja declarada es la envolvente del polígono
  de control: puede sobrar, nunca faltar.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

Point = tuple[float, float]
#: Un segmento del contorno: ("L", p) | ("Q", c, p) | ("C", c1, c2, p).
Segment = tuple

#: Familias de forma. Cada una fija rangos coherentes entre sí; lo que varía
#: dentro de una familia es la proporción, no la especie.
FAMILIES = (
    "inglés",
    "francés",
    "ibérico",
    "italiano",
    "torneo",
    "barroco",
    "estandarte",
    "ojival",
)

_MARGIN = 3.0

#: Con qué frecuencia aparece cada familia. El escudo de punta y el francés son
#: los que una persona reconoce como «escudo»; el cuadrado y el oval, en dosis
#: pequeñas, son los que evitan que la tanda parezca un juego de plantillas.
_FAMILY_WEIGHTS = {
    "inglés": 0.2,
    "francés": 0.2,
    "ibérico": 0.16,
    "ojival": 0.12,
    "torneo": 0.11,
    "italiano": 0.1,
    "barroco": 0.07,
    "estandarte": 0.03,
}


def _weighted_family(rng: random.Random) -> str:
    aguja = rng.random() * sum(_FAMILY_WEIGHTS.values())
    for nombre, peso in _FAMILY_WEIGHTS.items():
        aguja -= peso
        if aguja <= 0:
            return nombre
    return "francés"


def _fmt(value: float) -> str:
    texto = f"{value:.2f}".rstrip("0").rstrip(".")
    return texto or "0"


@dataclass(frozen=True)
class Escutcheon:
    """Una silueta concreta, con el porqué de su forma y su geometría viva.

    Guarda los segmentos, no sólo la cadena: la bordura interior se vuelve a
    emitir desde ellos, que es la única forma de que siga el borde de verdad.
    """

    start: Point
    segments: list[Segment]
    description: str
    family: str
    params: dict[str, float] = field(default_factory=dict)

    @property
    def d(self) -> str:
        return _render(self.start, self.segments)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        puntos = [self.start, *(punto for segmento in self.segments for punto in segmento[1:])]
        return (
            min(x for x, _ in puntos),
            min(y for _, y in puntos),
            max(x for x, _ in puntos),
            max(y for _, y in puntos),
        )

    def width_at(self, y: float) -> float:
        """Media anchura del escudo a esa altura.

        La necesita quien coloca los muebles: en un escudo de punta, a la
        altura de la campaña no cabe lo mismo que a la del jefe, y un mueble
        colocado por fuera de la silueta es el defecto más visible que hay.
        """
        half = self.params.get("half", 43.0)
        shoulder = self.params.get("shoulder", 34.0)
        arranque = self.params.get("arranque", 78.0)
        base_half = half * self.params.get("base_ratio", 0.4)
        bottom = self.params.get("bottom", 94.0)
        if y <= shoulder:
            return half
        hombro_ancho = base_half + (half - base_half) * 0.3
        if y <= arranque:
            t = (y - shoulder) / max(1e-6, arranque - shoulder)
            return max(4.0, half + (hombro_ancho - half) * t)
        t = min(1.0, (y - arranque) / max(1e-6, bottom - arranque))
        return max(3.0, hombro_ancho + (base_half * 0.35 - hombro_ancho) * t)

    def scaled(self, factor: float) -> Escutcheon:
        """La misma silueta encogida sobre su centro: la bordura interior."""
        cx, cy = 50.0, self.params.get("pivot_y", 52.0)

        def mover(punto: Point) -> Point:
            return (cx + (punto[0] - cx) * factor, cy + (punto[1] - cy) * factor)

        # Los parámetros se escalan con la silueta: quien coloca los muebles
        # pregunta por `width_at`, y una silueta encogida con los parámetros
        # viejos pondría las figuras fuera del borde.
        escalados = dict(self.params)
        for clave in ("half", "top", "bottom", "shoulder", "arranque"):
            if clave in escalados:
                valor = escalados[clave]
                escalados[clave] = valor * factor if clave == "half" else cy + (valor - cy) * factor
        return Escutcheon(
            start=mover(self.start),
            segments=[
                (segmento[0], *(mover(p) for p in segmento[1:])) for segmento in self.segments
            ],
            description=self.description,
            family=self.family,
            params=escalados,
        )


def _render(start: Point, segments: list[Segment]) -> str:
    partes = [f"M{_fmt(start[0])} {_fmt(start[1])}"]
    for segmento in segments:
        puntos = " ".join(f"{_fmt(x)} {_fmt(y)}" for x, y in segmento[1:])
        partes.append(f"{segmento[0]}{puntos}")
    partes.append("Z")
    return " ".join(partes)


def _mirror_point(punto: Point) -> Point:
    return (100.0 - punto[0], punto[1])


def _mirror(segments: list[Segment], start: Point) -> list[Segment]:
    """Refleja la mitad derecha y la recorre al revés, de la punta al jefe.

    Un segmento invertido no es el mismo segmento: en una cúbica los puntos de
    control se intercambian. Hacerlo mal da escudos con un hombro más alto que
    el otro.
    """
    salida: list[Segment] = []
    puntos = [start] + [segmento[-1] for segmento in segments]
    for indice in range(len(segments) - 1, -1, -1):
        segmento = segments[indice]
        destino = _mirror_point(puntos[indice])
        if segmento[0] == "L":
            salida.append(("L", destino))
        elif segmento[0] == "Q":
            salida.append(("Q", _mirror_point(segmento[1]), destino))
        else:
            salida.append(("C", _mirror_point(segmento[2]), _mirror_point(segmento[1]), destino))
    return salida


def _bouche(segments: list[Segment], half: float, top: float, rng: random.Random) -> list[Segment]:
    """Abre la muesca de lanza en el primer tramo del flanco derecho.

    Es un corte **hacia dentro**: la lanza apoya ahí. Dibujarlo hacia fuera es
    lo que convierte un escudo de torneo en un escudo con cuernos.
    """
    indice = next(
        (
            i
            for i, segmento in enumerate(segments)
            if segmento[0] == "L" and segmento[1][1] > top + 6
        ),
        None,
    )
    if indice is None:
        return segments
    destino = segments[indice][1]
    borde = 50 + half
    arriba = top + rng.uniform(5.0, 9.0)
    alto = rng.uniform(9.0, 14.0)
    hondo = rng.uniform(7.0, 11.0)
    if arriba + alto > destino[1] - 2:
        return segments
    corte: list[Segment] = [
        ("L", (borde, arriba)),
        (
            "C",
            (borde - hondo * 0.3, arriba),
            (borde - hondo, arriba + alto * 0.25),
            (borde - hondo, arriba + alto * 0.5),
        ),
        (
            "C",
            (borde - hondo, arriba + alto * 0.78),
            (borde - hondo * 0.3, arriba + alto),
            (borde, arriba + alto),
        ),
        ("L", destino),
    ]
    return segments[:indice] + corte + segments[indice + 1 :]


def _family_params(rng: random.Random, family: str, solidity: float) -> dict:
    """Rangos coherentes por familia. El `solidity` inclina, no decide."""
    ancho = 0.96 + solidity * 0.08
    if family == "inglés":  # heater: hombros rectos y punta
        return {
            "half": rng.uniform(38, 43) * ancho,
            "top": rng.uniform(6, 10),
            "corner": rng.uniform(0, 3),
            "shoulder": rng.uniform(27, 35),
            "flank": rng.uniform(-0.06, 0.06),
            "bottom": rng.uniform(92, 97),
            "base": "punta",
            "base_half": rng.uniform(0.06, 0.2),
            "chief": rng.choice(("recto", "recto", "arqueado")),
        }
    if family == "francés":  # écu moderne: base plana con uña
        return {
            "half": rng.uniform(41, 45) * ancho,
            "top": rng.uniform(6, 10),
            "corner": rng.uniform(2, 7),
            "shoulder": rng.uniform(32, 42),
            "flank": rng.uniform(-0.05, 0.04),
            "bottom": rng.uniform(88, 94),
            "base": "uña",
            "base_half": rng.uniform(0.34, 0.5),
            "chief": rng.choice(("recto", "recto", "abombado")),
        }
    if family == "ibérico":  # base semicircular
        return {
            "half": rng.uniform(41, 45) * ancho,
            "top": rng.uniform(6, 10),
            "corner": rng.uniform(1, 6),
            "shoulder": rng.uniform(34, 44),
            "flank": rng.uniform(-0.02, 0.07),
            "bottom": rng.uniform(90, 96),
            "base": "redonda",
            "base_half": rng.uniform(0.5, 0.75),
            "chief": rng.choice(("recto", "arqueado")),
        }
    if family == "italiano":  # oval, flancos convexos
        return {
            "half": rng.uniform(38, 42) * ancho,
            "top": rng.uniform(7, 12),
            "corner": rng.uniform(5, 10),
            "shoulder": rng.uniform(24, 31),
            "flank": rng.uniform(0.12, 0.24),
            "bottom": rng.uniform(90, 96),
            "base": "redonda",
            "base_half": rng.uniform(0.3, 0.5),
            "chief": rng.choice(("arqueado", "abombado")),
        }
    if family == "torneo":
        return {
            "half": rng.uniform(39, 44) * ancho,
            "top": rng.uniform(6, 10),
            "corner": rng.uniform(0, 4),
            "shoulder": rng.uniform(33, 42),
            "flank": rng.uniform(-0.2, -0.06),
            "bottom": rng.uniform(90, 96),
            "base": rng.choice(("punta", "ojival")),
            "base_half": rng.uniform(0.1, 0.3),
            "chief": "recto",
        }
    if family == "barroco":  # cintura marcada y punta rizada
        return {
            "half": rng.uniform(40, 44) * ancho,
            "top": rng.uniform(7, 11),
            "corner": rng.uniform(3, 9),
            "shoulder": rng.uniform(22, 29),
            "flank": rng.uniform(-0.28, -0.14),
            "bottom": rng.uniform(90, 96),
            "base": "rizada",
            "base_half": rng.uniform(0.3, 0.45),
            "chief": rng.choice(("escotado", "abombado", "arqueado")),
        }
    if family == "estandarte":  # flancos largos y base ancha
        return {
            "half": rng.uniform(42, 46) * ancho,
            "top": rng.uniform(5, 9),
            "corner": rng.uniform(0, 3),
            "shoulder": rng.uniform(46, 58),
            "flank": rng.uniform(-0.04, 0.03),
            "bottom": rng.uniform(86, 92),
            "base": "plana",
            "base_half": rng.uniform(0.58, 0.78),
            "chief": rng.choice(("recto", "escotado")),
        }
    return {
        "half": rng.uniform(39, 43) * ancho,
        "top": rng.uniform(5, 9),
        "corner": rng.uniform(0, 4),
        "shoulder": rng.uniform(26, 34),
        "flank": rng.uniform(-0.1, 0.02),
        "bottom": rng.uniform(93, 98),
        "base": "ojival",
        "base_half": rng.uniform(0.18, 0.34),
        "chief": rng.choice(("arqueado", "recto")),
    }


def escutcheon(
    rng: random.Random, *, solidity: float = 0.5, family: str | None = None
) -> Escutcheon:
    """Construye una silueta de escudo.

    `solidity` inclina la proporción —un club que se cuenta sólido lleva
    hombros algo más anchos—, pero no elige la forma: eso lo hace el azar
    reproducible del club.
    """
    family = family or _weighted_family(rng)
    p = _family_params(rng, family, solidity)
    half = min(50.0 - _MARGIN, p["half"])
    top, bottom, corner = p["top"], p["bottom"], p["corner"]
    shoulder, flank, chief = p["shoulder"], p["flank"], p["chief"]
    base_half = half * p["base_half"]
    chief_rise = rng.uniform(2.0, 6.0)

    inicio: Point = (50.0, top)
    segmentos: list[Segment] = []
    hombro_y = top + corner
    if chief == "arqueado":
        segmentos.append(("Q", (50 + half * 0.5, top - chief_rise * 0.8), (50 + half, hombro_y)))
    elif chief == "abombado":
        segmentos.append(("Q", (50 + half * 0.5, top + chief_rise), (50 + half, hombro_y)))
    elif chief == "escotado":
        inicio = (50.0, top + chief_rise * 0.55)
        segmentos.append(("Q", (50 + half * 0.45, top - 0.5), (50 + half, hombro_y)))
    elif corner > 1.2:
        segmentos.append(("L", (50 + half - corner * 0.9, top)))
        segmentos.append(("Q", (50 + half, top), (50 + half, hombro_y)))
    else:
        segmentos.append(("L", (50 + half, top)))
    segmentos.append(("L", (50 + half, shoulder)))

    # Flanco: una cúbica del hombro al arranque de la punta. La cintura es lo
    # que distingue un escudo barroco de uno inglés.
    arranque_y = bottom - (bottom - shoulder) * rng.uniform(0.16, 0.3)
    cintura_y = shoulder + (arranque_y - shoulder) * 0.55
    cintura_x = min(50 + half * (1 + flank * 0.4), 100 - _MARGIN)
    segmentos.append(
        (
            "C",
            (
                min(50 + half * (1 + flank * 0.2), 100 - _MARGIN),
                shoulder + (cintura_y - shoulder) * 0.45,
            ),
            (cintura_x, cintura_y),
            (50 + base_half + (half - base_half) * 0.3, arranque_y),
        )
    )

    base = p["base"]
    if base == "punta":
        segmentos.append(
            ("Q", (50 + base_half * 1.1, bottom - (bottom - arranque_y) * 0.35), (50.0, bottom))
        )
    elif base == "redonda":
        segmentos.append(
            ("C", (50 + base_half * 1.35, bottom), (50 + base_half * 0.8, bottom), (50.0, bottom))
        )
    elif base == "ojival":
        segmentos.append(("Q", (50 + base_half * 0.85, bottom - 1.5), (50.0, bottom)))
    elif base == "plana":
        segmentos.append(("Q", (50 + base_half * 1.05, bottom), (50 + base_half * 0.8, bottom)))
        segmentos.append(("L", (50.0, bottom)))
    elif base == "uña":
        segmentos.append(
            (
                "C",
                (50 + base_half * 1.15, bottom - 4),
                (50 + base_half * 0.9, bottom - 2.2),
                (50 + base_half * 0.5, bottom - 2.2),
            )
        )
        segmentos.append(("Q", (50 + base_half * 0.2, bottom - 2.2), (50.0, bottom)))
    else:  # rizada
        segmentos.append(
            (
                "C",
                (50 + base_half * 1.45, bottom - 2.5),
                (50 + base_half * 1.0, bottom - 8),
                (50 + base_half * 0.5, bottom - 4.5),
            )
        )
        segmentos.append(("Q", (50 + base_half * 0.22, bottom - 1.5), (50.0, bottom)))

    completos = segmentos + _mirror(segmentos, inicio)
    muesca = family == "torneo" or (family in ("inglés", "francés") and rng.random() < 0.12)
    if muesca:
        completos = _bouche(completos, half, top, rng)
    descripcion = (
        f"escudo {family}: jefe {chief}, "
        f"flanco {'de cintura' if flank < -0.1 else 'convexo' if flank > 0.08 else 'recto'}, "
        f"punta {base}" + (", con muesca de lanza" if muesca else "")
    )
    return Escutcheon(
        start=inicio,
        segments=completos,
        description=descripcion,
        family=family,
        params={
            "half": half,
            "top": top,
            "bottom": bottom,
            "shoulder": shoulder,
            "arranque": arranque_y,
            "base_ratio": p["base_half"],
            "pivot_y": (top + bottom) / 2,
        },
    )
