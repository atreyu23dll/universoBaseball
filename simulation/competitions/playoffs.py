"""Postemporada: siembra, brackets y series al mejor de N.

No se puede armar un playoff de N si clasificaron menos de N: se rechaza con un
error explícito en vez de inventar participantes.

Con grupos, divisiones o conferencias la siembra no sale de la tabla general:
clasifican los primeros de cada grupo y, si el reglamento lo declara, los
mejores no clasificados de la tabla general como repechaje. Es la diferencia
entre «los mejores ocho» y «los campeones de división más dos comodines», y
cambia quién juega: un grupo fuerte puede meter a tres clubes y uno flojo solo
a su campeón.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from hashlib import sha256

from simulation.competitions.ruleset import (
    PairingPolicy,
    PlayoffFormat,
    PlayoffRules,
    StructureRules,
)
from simulation.competitions.structure import Gate, GateRoute, Stage
from simulation.core.errors import RuleValidationError


@dataclass(frozen=True)
class PlayoffGame:
    round_index: int
    series_key: str
    game_in_series: int
    home_key: str
    away_key: str
    game_date: date


@dataclass
class PlayoffSeries:
    series_key: str
    round_index: int
    high_seed: str
    low_seed: str
    best_of: int
    wins: dict[str, int] = field(default_factory=dict)

    @property
    def needed(self) -> int:
        return self.best_of // 2 + 1

    @property
    def winner(self) -> str | None:
        for key, count in self.wins.items():
            if count >= self.needed:
                return key
        return None

    def home_key_for(self, game_in_series: int) -> tuple[str, str]:
        """Patrón de localías 2-2-1 simplificado: la mejor siembra abre en casa.

        Los dos primeros y el último se juegan en casa de la mejor siembra.
        """
        if self.best_of == 1:
            return self.high_seed, self.low_seed
        away_games = {2, 3} if self.best_of >= 5 else {1}
        if game_in_series in away_games:
            return self.low_seed, self.high_seed
        return self.high_seed, self.low_seed


@dataclass(frozen=True)
class Qualifier:
    """Un clasificado y por qué lo está."""

    entry_key: str
    #: `group_winner` si entró por su grupo, `wildcard` si por repechaje,
    #: `overall` cuando la competición no tiene grupos.
    route: str
    group_key: str = ""
    #: Puesto en su grupo, cuando entró por él.
    group_rank: int = 0
    reason: str = ""
    #: Ronda en la que entra, si el cuadro fue colocado a mano. ``None`` usa
    #: los pases automáticos por siembra del formato clásico.
    entry_round: int | None = None
    entry_order: int | None = None


def qualifiers_from_gates(
    ranked: list[tuple[str, str]],
    stage: Stage,
    slots: int,
) -> list[Qualifier]:
    """Quién sale de una fase, por qué puerta y por qué.

    `ranked` son los participantes en orden de la tabla general, con la
    **etiqueta** de su división.

    Se resuelve en dos pasadas, y el orden importa:

    1. Las puertas **de división** toman su puesto dentro de su división.
    2. Las puertas **de la tabla general** toman su puesto entre los que no
       pasaron por ninguna división. Todas miran la *misma* lista de
       descartados, así que «el mejor de los que se quedaron fuera» significa
       lo mismo esté esa plaza en una puerta o repartida en varias: la
       numeración no se desplaza por cómo el editor agrupe las puertas.

    El orden de siembra final es el de la tabla general, salvo que el editor
    haya dibujado el cuadro, y entonces manda el orden que dibujó.
    """
    orden = {key: indice for indice, (key, _) in enumerate(ranked)}
    division_de = {d.key: d.label for d in stage.divisions}
    clasificados: list[Qualifier] = []

    def resolver(gate: Gate, candidatos: list[tuple[str, str]], division: str | None) -> None:
        for offset, puesto in enumerate(gate.positions):
            if puesto > len(candidatos):
                continue
            clave, grupo = candidatos[puesto - 1]
            clasificados.append(
                Qualifier(
                    entry_key=clave,
                    route=_gate_route(gate),
                    group_key=grupo,
                    group_rank=puesto if gate.division else 0,
                    reason=_gate_reason(gate, puesto, division),
                    entry_round=gate.target_round,
                    entry_order=(gate.order + offset if gate.order is not None else None),
                )
            )

    por_division = [g for g in stage.gates if g.division is not None]
    de_la_tabla = [g for g in stage.gates if g.division is None]

    ya_pasaron: set[str] = set()
    for gate in por_division:
        etiqueta = division_de.get(gate.division, gate.division or "")
        candidatos = [(k, g) for k, g in ranked if g == etiqueta and k not in ya_pasaron]
        antes = len(clasificados)
        resolver(gate, candidatos, etiqueta)
        ya_pasaron |= {q.entry_key for q in clasificados[antes:]}

    descartados = [(k, g) for k, g in ranked if k not in ya_pasaron]
    for gate in de_la_tabla:
        resolver(gate, descartados, None)

    if len(clasificados) < slots:
        raise RuleValidationError(
            f"las puertas de «{stage.label}» produjeron {len(clasificados)} clasificados "
            f"y la fase siguiente pide {slots}",
            [
                "revisa los puestos de cada puerta",
                "o comprueba que ninguna división se haya quedado sin clubes",
            ],
        )
    if clasificados and all(q.entry_order is not None for q in clasificados):
        return sorted(clasificados, key=lambda q: int(q.entry_order or 0))[:slots]
    return sorted(clasificados, key=lambda q: orden[q.entry_key])[:slots]


def _gate_route(gate: Gate) -> str:
    """Cómo se describe la entrada de una puerta en los eventos y el cuadro.

    Una puerta neutra —las que dibuja el editor— no trae etiqueta deportiva: su
    ruta la dice su procedencia. Si sale de una división es el puesto de su
    división; si sale de la tabla general es una plaza entre los descartados,
    que es lo que siempre se llamó repechaje.
    """
    if gate.route is GateRoute.WILDCARD:
        return "wildcard"
    if gate.division is None:
        return "wildcard" if gate.route is GateRoute.SEED else "overall"
    return "group_winner"


def _gate_reason(gate: Gate, puesto: int, division: str | None) -> str:
    if gate.label:
        return f"{gate.label} ({_ordinal(puesto)})" if len(gate.positions) > 1 else gate.label
    if gate.route is GateRoute.WILDCARD or (gate.route is GateRoute.SEED and gate.division is None):
        return (
            "mejor registro entre los no clasificados"
            if puesto == 1
            else f"{_ordinal(puesto)} entre los no clasificados"
        )
    if division is None:
        return f"{_ordinal(puesto)} de la tabla"
    return f"campeón de {division}" if puesto == 1 else f"{_ordinal(puesto)} de {division}"


def qualifiers_from_groups(
    ranked: list[tuple[str, str]],
    structure: StructureRules,
    rules: PlayoffRules,
) -> list[Qualifier]:
    """Clasificados de la primera fase, venga de donde venga la estructura.

    Es una envoltura: traduce la estructura a fases —las declaradas por el
    usuario o las que implica la forma simple— y resuelve sus puertas. Así hay
    **una sola** implementación de «quién clasifica», y un reglamento viejo y
    uno nuevo recorren el mismo camino.
    """
    if rules.format is PlayoffFormat.NONE:
        return []
    if not structure.has_groups and not structure.declared:
        return [
            Qualifier(entry_key=key, route="overall", group_key=grupo, reason="puesto en la tabla")
            for key, grupo in ranked[: rules.slots]
        ]
    fases = structure.effective_stages(len(ranked), rules)
    return qualifiers_from_gates(ranked, fases[0], rules.slots)


def _ordinal(puesto: int) -> str:
    return {1: "primero", 2: "segundo", 3: "tercero", 4: "cuarto"}.get(puesto, f"{puesto}.º")


def seed_bracket(
    ranked_entry_keys: list[str], rules: PlayoffRules
) -> tuple[list[PlayoffSeries], list[str]]:
    """Primera ronda del cuadro y quiénes la esperan con pase directo.

    Cuando las plazas no son potencia de dos —seis, por ejemplo: dos campeones
    de división y dos repechajes— el cuadro se completa con **pases directos**
    para las mejores siembras, que es lo que hacen las ligas de verdad en vez de
    redondear el número de clasificados. Con seis plazas, las siembras 1 y 2
    esperan en la segunda ronda y 3-6 y 4-5 juegan la primera.
    """
    if rules.format is PlayoffFormat.NONE:
        return [], []
    if len(ranked_entry_keys) < rules.slots:
        raise RuleValidationError(
            f"el playoff pide {rules.slots} clasificados pero la clasificación "
            f"solo tiene {len(ranked_entry_keys)} participantes",
            [
                f"reduce `playoffs.slots` a {len(ranked_entry_keys)} o menos",
                "o aumenta el número de clubes de la competición",
            ],
        )
    qualified = ranked_entry_keys[: rules.slots]
    best_of = rules.round_lengths[0] if rules.round_lengths else 1

    byes = qualified[: rules.byes]
    juegan = qualified[rules.byes :]
    series: list[PlayoffSeries] = []
    for i in range(len(juegan) // 2):
        high = juegan[i]
        low = juegan[len(juegan) - 1 - i]
        series.append(
            PlayoffSeries(
                series_key=f"r0s{i}",
                round_index=0,
                high_seed=high,
                low_seed=low,
                best_of=best_of,
                wins={high: 0, low: 0},
            )
        )
    return series, byes


def seed_staged_bracket(
    qualifiers: list[Qualifier],
    rules: PlayoffRules,
    seed_order: list[str] | None = None,
) -> tuple[list[PlayoffSeries], list[dict[str, int | str]]]:
    """Siembra un cuadro cuyas entradas se colocaron en rondas concretas.

    La diferencia frente a :func:`seed_bracket` es que los pases no se
    infieren por potencia de dos: son exactamente los cajones que el usuario
    dibujó. Cada entrada que no empieza en la primera ronda queda pendiente con
    su número de ronda, y la espera ahí hasta que le toque.

    `qualifiers` viene en el orden dibujado —el que manda cuando las llaves son
    fijas— y `seed_order` es la tabla de la temporada regular, que es la que
    manda cuando la ronda resiembra. Sin tabla, el orden dibujado hace las dos
    cosas.
    """
    if len(qualifiers) < rules.slots:
        raise RuleValidationError(
            f"el playoff pide {rules.slots} clasificados pero solo recibió {len(qualifiers)}"
        )
    selected = qualifiers[: rules.slots]
    if any(item.entry_round is None for item in selected):
        raise RuleValidationError(
            "el cuadro editable necesita que todas sus entradas estén colocadas en una ronda"
        )
    first = [item.entry_key for item in selected if item.entry_round == 0]
    pending = [
        {"club_id": item.entry_key, "round": int(item.entry_round or 0)}
        for item in selected
        if (item.entry_round or 0) > 0
    ]
    tabla = list(seed_order) if seed_order else [q.entry_key for q in selected]
    return pair_round(first, tabla, rules, 0), pending


def pair_round(
    entries: list[str], seed_order: list[str], rules: PlayoffRules, round_index: int
) -> list[PlayoffSeries]:
    """Forma los cruces de una ronda con la política que pida el reglamento.

    `entries` llega en el orden que importa cuando no hay resiembra: el que
    dibujó el editor en la primera ronda y el de los cruces de la ronda
    anterior en las siguientes.
    """
    if len(entries) < 2 or len(entries) % 2:
        raise RuleValidationError(
            f"la ronda {round_index + 1} recibe {len(entries)} participantes y no forma "
            "cruces completos"
        )
    policy = rules.pairing_for(round_index)
    ordered = _ordered_for_pairing(entries, seed_order, policy, round_index)
    pairs = [_by_seed(pair, seed_order) for pair in _pair_keys(ordered, policy)]
    best_of = rules.best_of_for(round_index)
    return [
        PlayoffSeries(
            series_key=f"r{round_index}s{i}",
            round_index=round_index,
            high_seed=high,
            low_seed=low,
            best_of=best_of,
            wins={high: 0, low: 0},
        )
        for i, (high, low) in enumerate(pairs)
    ]


def _ordered_for_pairing(
    entries: list[str], seed_order: list[str], policy: PairingPolicy, round_index: int
) -> list[str]:
    """Ordena a los participantes antes de cruzarlos.

    Con llaves fijas no se toca el orden recibido: el cuadro es el dibujado y
    el ganador de un cruce espera al del cruce de al lado. Con las demás
    políticas se resiembra por la tabla, y el sorteo baraja de forma
    reproducible: el mismo reglamento da siempre los mismos cruces.
    """
    if policy is PairingPolicy.FIXED:
        return list(entries)
    ordered = sorted(entries, key=lambda key: _seed_index(key, seed_order))
    if policy is PairingPolicy.DRAW:
        ordered.sort(key=lambda key: sha256(f"{round_index}:{key}".encode()).hexdigest())
    return ordered


def _pair_keys(ordered: list[str], policy: PairingPolicy) -> list[tuple[str, str]]:
    if policy is PairingPolicy.HIGH_LOW:
        return [(ordered[i], ordered[-1 - i]) for i in range(len(ordered) // 2)]
    return [(ordered[i], ordered[i + 1]) for i in range(0, len(ordered), 2)]


def _seed_index(key: str, seed_order: list[str]) -> int:
    """Puesto del club en la tabla. Uno que no esté se cruza al final."""
    try:
        return seed_order.index(key)
    except ValueError:
        return len(seed_order)


def _by_seed(pair: tuple[str, str], seed_order: list[str]) -> tuple[str, str]:
    """La localía la abre el mejor clasificado de la pareja, cruce como sea."""
    uno, otro = pair
    if _seed_index(otro, seed_order) < _seed_index(uno, seed_order):
        return otro, uno
    return uno, otro


def next_round(
    previous: list[PlayoffSeries],
    seed_order: list[str],
    rules: PlayoffRules,
    waiting: list[str] | None = None,
) -> list[PlayoffSeries]:
    """Construye la ronda siguiente con los ganadores y los que la esperaban.

    `waiting` son los clasificados que entran en esta ronda: los pases directos
    del cuadro deducido y, en un cuadro dibujado, las plazas que el usuario
    colocó aquí. Entran a la ronda como cualquier otro superviviente, y cómo se
    cruzan lo decide la política de la ronda: la resiembra de la tabla, las
    llaves fijas del cuadro o un sorteo.
    """
    winners = [s.winner for s in previous]
    if any(w is None for w in winners):
        raise RuleValidationError("hay series de la ronda anterior sin resolver")
    # Los ganadores se toman en el orden de los cruces de los que salen: es lo
    # que permite que una llave fija espere a la de al lado.
    advancing = [w for w in winners if w is not None] + list(waiting or ())
    if len(advancing) < 2:
        return []
    return pair_round(advancing, seed_order, rules, previous[0].round_index + 1)


def schedule_series_game(
    series: PlayoffSeries,
    game_in_series: int,
    game_date: date,
) -> PlayoffGame:
    home, away = series.home_key_for(game_in_series)
    return PlayoffGame(
        round_index=series.round_index,
        series_key=series.series_key,
        game_in_series=game_in_series,
        home_key=home,
        away_key=away,
        game_date=game_date,
    )


def next_playoff_date(previous: date, rest_days_weekday: list[int]) -> date:
    day = previous + timedelta(days=1)
    rest = set(rest_days_weekday)
    while day.weekday() in rest:
        day += timedelta(days=1)
    return day
