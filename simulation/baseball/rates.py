"""Tasas base de liga y resolución del duelo bateador–lanzador.

El método: para cada resultado posible de un turno al bate se parte de una tasa
base de liga y se la desplaza en espacio logarítmico según la diferencia de
habilidad relevante entre bateador y lanzador (un log5 multiplicativo). Lo que
sobra tras repartir los resultados discretos es "out con la pelota en juego",
que después se resuelve en el campo.

Las tasas base de referencia corresponden a un entorno profesional y están
deliberadamente cerca de las proporciones del béisbol profesional moderno. El
ajuste por nivel de competición (más boletos y más errores en categorías
modestas) es una **heurística sin calibrar empíricamente**; ver
`docs/simulation-calibration.md`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from simulation.people.model import Person

# Tasas por turno al bate en un entorno profesional de referencia.
BASE_WALK = 0.085
BASE_HBP = 0.009
BASE_STRIKEOUT = 0.210
BASE_HOMERUN = 0.0275
BASE_TRIPLE = 0.004
BASE_DOUBLE = 0.045
BASE_SINGLE = 0.145

# Sensibilidad de cada resultado a la diferencia de habilidad. Cuanto mayor,
# más separa a los buenos de los malos.
# Calibradas contra la dispersión de promedios individuales del béisbol
# profesional (sd ≈ 0.028 entre bateadores con turnos suficientes). Subirlas
# separa más a los buenos de los malos, pero produce campeones de bateo de .430
# y campeones de liga de .730, que no se parecen a nada real.
SENS_WALK = 1.30
SENS_STRIKEOUT = 1.25
SENS_HOMERUN = 1.70
SENS_EXTRA_BASE = 1.10
SENS_SINGLE = 0.72

# Errores de fildeo por bola en juego, por nivel de competición.
BASE_ERROR_PRO = 0.011
BASE_ERROR_AMATEUR = 0.050


@dataclass(frozen=True)
class LeagueRates:
    """Entorno ofensivo de una competición concreta."""

    walk: float
    hbp: float
    strikeout: float
    homerun: float
    triple: float
    double: float
    single: float
    error_rate: float
    hit_on_ball_in_play_bonus: float
    professionalization: float

    @classmethod
    def for_level(cls, professionalization: float) -> LeagueRates:
        """Deriva el entorno de una liga de su nivel, 0-1.

        Una liga amateur tiene más boletos (menos control), más ponches (menos
        contacto), menos jonrones (menos potencia) y bastantes más errores. Una
        liga de élite aprieta en todo.
        """
        level = max(0.0, min(1.0, professionalization))
        gap = 0.5 - level  # positivo si está por debajo del nivel de referencia
        return cls(
            walk=BASE_WALK * (1.0 + 0.55 * gap),
            hbp=BASE_HBP * (1.0 + 0.9 * gap),
            strikeout=BASE_STRIKEOUT * (1.0 + 0.35 * gap),
            homerun=BASE_HOMERUN * (1.0 - 0.75 * gap),
            triple=BASE_TRIPLE * (1.0 + 0.6 * gap),
            double=BASE_DOUBLE * (1.0 - 0.1 * gap),
            single=BASE_SINGLE * (1.0 + 0.12 * gap),
            error_rate=BASE_ERROR_AMATEUR + (BASE_ERROR_PRO - BASE_ERROR_AMATEUR) * level,
            hit_on_ball_in_play_bonus=0.22 * gap,
            professionalization=level,
        )


@dataclass(slots=True)
class BatterProfile:
    """Lo que el motor necesita de un bateador, precalculado una vez."""

    key: str
    contact: float
    power: float
    discipline: float
    strikeout_avoidance: float
    speed: float
    fly_ball_rate: float
    composure: float

    @classmethod
    def of(cls, person: Person) -> BatterProfile:
        b = person.batting
        return cls(
            key=person.key,
            contact=b.contact,
            power=b.power,
            discipline=b.discipline,
            strikeout_avoidance=b.strikeout_avoidance,
            speed=b.speed,
            fly_ball_rate=0.30 + 0.25 * b.power,
            composure=person.cognition.composure,
        )


@dataclass(slots=True)
class PitcherProfile:
    key: str
    stuff: float
    control: float
    movement: float
    stamina: float
    hold_runners: float
    composure: float
    max_pitches: int

    @classmethod
    def of(cls, person: Person, is_starter: bool) -> PitcherProfile:
        p = person.pitching
        ceiling = (62 + 50 * p.stamina) if is_starter else (18 + 28 * p.stamina)
        return cls(
            key=person.key,
            stuff=p.stuff,
            control=p.control,
            movement=p.movement,
            stamina=p.stamina,
            hold_runners=p.hold_runners,
            composure=person.cognition.composure,
            max_pitches=int(round(ceiling)),
        )


PlateOutcome = int

OUT_IN_PLAY = 0
SINGLE = 1
DOUBLE = 2
TRIPLE = 3
HOMERUN = 4
WALK = 5
HIT_BY_PITCH = 6
STRIKEOUT = 7


def _shift(base: float, delta: float, sensitivity: float) -> float:
    """Desplaza una tasa base por una diferencia de habilidad.

    Multiplicativo en espacio logarítmico: una ventaja de +0.2 en la habilidad
    relevante multiplica la tasa por exp(sens*0.2). Nunca puede volverla
    negativa, que es la razón de no usar una suma.
    """
    return base * math.exp(sensitivity * delta)


def plate_probabilities(
    batter: BatterProfile,
    pitcher: PitcherProfile,
    rates: LeagueRates,
    fatigue_penalty: float,
    hr_park_factor: float,
    xbh_park_factor: float,
) -> tuple[float, float, float, float, float, float, float]:
    """Devuelve (BB, HBP, K, HR, 3B, 2B, 1B). El resto es out en juego.

    `fatigue_penalty` ∈ [0, 1] degrada al lanzador: resta de sus habilidades
    efectivas, lo que sube boletos y batazos en su contra.
    """
    stuff = pitcher.stuff - fatigue_penalty * 0.30
    control = pitcher.control - fatigue_penalty * 0.38
    movement = pitcher.movement - fatigue_penalty * 0.25

    walk = _shift(rates.walk, (batter.discipline - 0.5) - (control - 0.5), SENS_WALK)
    hbp = _shift(rates.hbp, -(control - 0.5), 0.8)
    strikeout = _shift(
        rates.strikeout, (stuff - 0.5) - (batter.strikeout_avoidance - 0.5), SENS_STRIKEOUT
    )
    homerun = (
        _shift(rates.homerun, (batter.power - 0.5) - (movement - 0.5), SENS_HOMERUN)
        * hr_park_factor
    )
    triple = (
        _shift(
            rates.triple,
            (0.6 * batter.speed + 0.4 * batter.power - 0.5) - (movement - 0.5),
            SENS_EXTRA_BASE,
        )
        * xbh_park_factor
    )
    double = (
        _shift(
            rates.double,
            (0.6 * batter.power + 0.4 * batter.contact - 0.5) - (movement - 0.5),
            SENS_EXTRA_BASE,
        )
        * xbh_park_factor
    )
    single = _shift(
        rates.single,
        (batter.contact - 0.5)
        - (0.5 * stuff + 0.5 * movement - 0.5)
        + rates.hit_on_ball_in_play_bonus,
        SENS_SINGLE,
    )

    total = walk + hbp + strikeout + homerun + triple + double + single
    # Tope de seguridad: el turno al bate siempre deja sitio a un out en juego.
    # Sin esto, una combinación extrema de atributos podría sumar más de 1.
    cap = 0.93
    if total > cap:
        scale = cap / total
        walk *= scale
        hbp *= scale
        strikeout *= scale
        homerun *= scale
        triple *= scale
        double *= scale
        single *= scale
    return walk, hbp, strikeout, homerun, triple, double, single


def resolve_plate_appearance(
    roll: float,
    probabilities: tuple[float, float, float, float, float, float, float],
) -> PlateOutcome:
    """Convierte un número aleatorio en un resultado del turno al bate."""
    walk, hbp, strikeout, homerun, triple, double, single = probabilities
    acc = walk
    if roll < acc:
        return WALK
    acc += hbp
    if roll < acc:
        return HIT_BY_PITCH
    acc += strikeout
    if roll < acc:
        return STRIKEOUT
    acc += homerun
    if roll < acc:
        return HOMERUN
    acc += triple
    if roll < acc:
        return TRIPLE
    acc += double
    if roll < acc:
        return DOUBLE
    acc += single
    if roll < acc:
        return SINGLE
    return OUT_IN_PLAY
