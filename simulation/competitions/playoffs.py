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

from simulation.competitions.ruleset import PlayoffFormat, PlayoffRules, StructureRules
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


def qualifiers_from_gates(
    ranked: list[tuple[str, str]],
    stage: Stage,
    slots: int,
) -> list[Qualifier]:
    """Quién sale de una fase, por qué puerta y por qué.

    `ranked` son los participantes en orden de la tabla general, con la
    **etiqueta** de su división. Las puertas se resuelven en el orden en que se
    declararon, y eso importa: una puerta de la tabla general cuenta sus puestos
    entre los que **todavía no han pasado**, que es lo que significa un
    repechaje.

    El orden de siembra final es el de la tabla general, de modo que un campeón
    de división flojo no siembra por encima de uno mejor.
    """
    orden = {key: indice for indice, (key, _) in enumerate(ranked)}
    division_de = {d.key: d.label for d in stage.divisions}
    ya_pasaron: set[str] = set()
    clasificados: list[Qualifier] = []

    for gate in stage.gates:
        if gate.division is None:
            candidatos = [(k, g) for k, g in ranked if k not in ya_pasaron]
            etiqueta_division = None
        else:
            etiqueta_division = division_de.get(gate.division, gate.division)
            candidatos = [
                (k, g) for k, g in ranked if g == etiqueta_division and k not in ya_pasaron
            ]
        for puesto in gate.positions:
            if puesto > len(candidatos):
                continue
            clave, grupo = candidatos[puesto - 1]
            ya_pasaron.add(clave)
            clasificados.append(
                Qualifier(
                    entry_key=clave,
                    route=("wildcard" if gate.route is GateRoute.WILDCARD else "group_winner"),
                    group_key=grupo,
                    group_rank=puesto if gate.division else 0,
                    reason=_gate_reason(gate, puesto, etiqueta_division),
                )
            )

    if len(clasificados) < slots:
        raise RuleValidationError(
            f"las puertas de «{stage.label}» produjeron {len(clasificados)} clasificados "
            f"y la fase siguiente pide {slots}",
            [
                "revisa los puestos de cada puerta",
                "o comprueba que ninguna división se haya quedado sin clubes",
            ],
        )
    return sorted(clasificados, key=lambda q: orden[q.entry_key])[:slots]


def _gate_reason(gate: Gate, puesto: int, division: str | None) -> str:
    if gate.label:
        return f"{gate.label} ({_ordinal(puesto)})" if len(gate.positions) > 1 else gate.label
    if gate.route is GateRoute.WILDCARD:
        return (
            "repechaje: mejor registro entre los no clasificados"
            if puesto == 1
            else (f"repechaje: {_ordinal(puesto)} entre los no clasificados")
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


def next_round(
    previous: list[PlayoffSeries],
    seed_order: list[str],
    rules: PlayoffRules,
    waiting: list[str] | None = None,
) -> list[PlayoffSeries]:
    """Construye la ronda siguiente con los ganadores, resembrando por siembra.

    `waiting` son los clasificados con pase directo que entran en esta ronda. La
    resiembra los trata como a cualquier otro: el mejor de la temporada regular
    se cruza con el peor de los que siguen vivos.
    """
    winners = [s.winner for s in previous]
    if any(w is None for w in winners):
        raise RuleValidationError("hay series de la ronda anterior sin resolver")
    advancing = [w for w in winners if w is not None] + list(waiting or ())
    if len(advancing) < 2:
        return []

    round_index = previous[0].round_index + 1
    best_of = (
        rules.round_lengths[round_index]
        if round_index < len(rules.round_lengths)
        else previous[0].best_of
    )
    # Resiembra: el mejor clasificado de la temporada regular se cruza con el
    # peor de los que siguen vivos.
    advancing.sort(key=lambda key: seed_order.index(key))
    series: list[PlayoffSeries] = []
    for i in range(len(advancing) // 2):
        high = advancing[i]
        low = advancing[len(advancing) - 1 - i]
        series.append(
            PlayoffSeries(
                series_key=f"r{round_index}s{i}",
                round_index=round_index,
                high_seed=high,
                low_seed=low,
                best_of=best_of,
                wins={high: 0, low: 0},
            )
        )
    return series


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
