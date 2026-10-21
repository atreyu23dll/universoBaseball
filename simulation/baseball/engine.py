"""Motor de partidos, nivel 1: turno al bate por turno al bate.

Lo importante de este archivo es lo que **no** hace: no decide un ganador y
luego inventa un box score. Resuelve cada turno al bate, mueve corredores,
cuenta outs y anota carreras; el marcador es la suma de esas carreras y las
estadísticas son el registro de esos eventos. Después del último out, el
resultado pasa por `simulation.core.invariants.check_game_result`, que revienta
si la contabilidad no cierra.

Lo que todavía no es: no hay lanzamiento por lanzamiento, ni conteo de bolas y
strikes, ni trayectoria física de la pelota (niveles 2 y 3, Etapa 5). La
interfaz `simulate_game` está pensada para que esos niveles entren al lado,
calibrados contra este.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from simulation.baseball.lineup import TeamSetup, build_setup
from simulation.baseball.park import NEUTRAL_PARK, ParkFactors
from simulation.baseball.rates import (
    DOUBLE,
    HIT_BY_PITCH,
    HOMERUN,
    OUT_IN_PLAY,
    SINGLE,
    STRIKEOUT,
    TRIPLE,
    WALK,
    BatterProfile,
    LeagueRates,
    PitcherProfile,
    plate_probabilities,
    resolve_plate_appearance,
)
from simulation.baseball.result import (
    BattingLine,
    FieldingLine,
    GameResult,
    GameState,
    PitchingLine,
    TeamBox,
)
from simulation.competitions.ruleset import SeasonRules
from simulation.core.errors import InvariantViolation
from simulation.core.invariants import check_game_result
from simulation.core.rng import rng_for
from simulation.geography.weather import WeatherSample
from simulation.organizations.model import Club, Venue
from simulation.people.model import Person, Position

ENGINE_VERSION = "fast_pa_engine/1.0.0"

REGULATION_INNINGS = 9
#: Desde esta entrada extra se coloca un corredor automático en segunda. Es la
#: regla moderna de resolución rápida; su carrera no es limpia, como manda el
#: reglamento. Sin esto un empate puede estirarse indefinidamente.
AUTOMATIC_RUNNER_FROM_INNING = 11
#: Tope absoluto. Si se alcanza, el partido queda SUSPENDIDO, que es un estado
#: definido: la especificación prohíbe que un partido no termine ni se declare.
MAX_INNINGS = 30

_PITCHES_BY_OUTCOME = {
    STRIKEOUT: 4.8,
    WALK: 5.6,
    HIT_BY_PITCH: 3.4,
    HOMERUN: 3.6,
    TRIPLE: 3.3,
    DOUBLE: 3.4,
    SINGLE: 3.3,
    OUT_IN_PLAY: 3.5,
}

_INFIELD = (
    Position.FIRST_BASE,
    Position.SECOND_BASE,
    Position.THIRD_BASE,
    Position.SHORTSTOP,
)
_OUTFIELD = (Position.LEFT_FIELD, Position.CENTER_FIELD, Position.RIGHT_FIELD)


@dataclass(slots=True)
class Runner:
    """Un corredor en base.

    `responsible_pitcher_key` es quien lo puso ahí: si anota, la carrera se le
    carga a él, no al que esté en el montículo. `earned` es falso cuando llegó
    por error o es corredor automático de entrada extra.
    """

    person_key: str
    responsible_pitcher_key: str
    earned: bool = True


@dataclass
class TeamGameInput:
    club: Club
    roster: dict[str, Person]
    club_game_index: int = 0
    rest_days: dict[str, int] = field(default_factory=dict)


@dataclass
class _TeamState:
    setup: TeamSetup
    box: TeamBox
    batters: dict[str, BatterProfile]
    batting_lines: dict[str, BattingLine]
    fielding_lines: dict[str, FieldingLine]
    pitching_lines: dict[str, PitchingLine]
    roster: dict[str, Person]
    lineup_index: int = 0
    current_pitcher_key: str = ""
    current_profile: PitcherProfile | None = None
    bullpen_queue: list[str] = field(default_factory=list)
    closer_key: str | None = None
    times_through_order: int = 0

    @property
    def runs(self) -> int:
        return sum(self.box.line_score)

    def current_pitching_line(self) -> PitchingLine:
        return self.pitching_lines[self.current_pitcher_key]


def _new_team_state(team: TeamGameInput, uses_dh: bool) -> _TeamState:
    setup = build_setup(
        club_key=team.club.key,
        roster=team.roster,
        club_game_index=team.club_game_index,
        uses_dh=uses_dh,
        rest_days=team.rest_days,
    )
    box = TeamBox(club_key=team.club.key)
    batting_lines: dict[str, BattingLine] = {}
    fielding_lines: dict[str, FieldingLine] = {}
    for slot, person_key in enumerate(setup.batting_order, start=1):
        batting_lines[person_key] = BattingLine(
            person_key=person_key,
            lineup_slot=slot,
            position=setup.positions.get(person_key, "DH"),
        )
    for person_key, position in setup.positions.items():
        fielding_lines[person_key] = FieldingLine(person_key=person_key, position=position)
    box.batting = list(batting_lines.values())
    box.fielding = list(fielding_lines.values())

    starter = team.roster[setup.starter_key]
    starter_line = PitchingLine(person_key=starter.key, is_starter=True, entered_inning=1)
    state = _TeamState(
        setup=setup,
        box=box,
        batters={k: BatterProfile.of(team.roster[k]) for k in setup.batting_order},
        batting_lines=batting_lines,
        fielding_lines=fielding_lines,
        pitching_lines={starter.key: starter_line},
        roster=team.roster,
        current_pitcher_key=starter.key,
        current_profile=PitcherProfile.of(starter, is_starter=True),
        bullpen_queue=list(setup.bullpen),
        closer_key=setup.closer_key,
    )
    box.pitching = [starter_line]
    return state


def _fatigue_penalty(line: PitchingLine, profile: PitcherProfile) -> float:
    """Degradación del lanzador. Empieza al 75% de su capacidad."""
    threshold = profile.max_pitches * 0.75
    if line.pitches <= threshold:
        return 0.0
    over = (line.pitches - threshold) / max(1.0, profile.max_pitches * 0.55)
    return min(1.0, over)


def _ensure_fielding_line(state: _TeamState, person_key: str, position: str) -> FieldingLine:
    line = state.fielding_lines.get(person_key)
    if line is None:
        line = FieldingLine(person_key=person_key, position=position)
        state.fielding_lines[person_key] = line
        state.box.fielding.append(line)
    return line


def _fielder_for(state: _TeamState, rng: random.Random, is_fly: bool) -> tuple[str, str]:
    """Quién atiende la pelota. Devuelve (person_key, posición)."""
    wanted = _OUTFIELD if is_fly else _INFIELD
    candidates = [
        (key, pos) for key, pos in state.setup.positions.items() if pos in {str(p) for p in wanted}
    ]
    if not candidates:
        candidates = [
            (key, pos)
            for key, pos in state.setup.positions.items()
            if pos != str(Position.DESIGNATED_HITTER)
        ]
    if not candidates:
        return state.current_pitcher_key, str(Position.PITCHER)
    return rng.choice(candidates)


@dataclass
class _LeadTracker:
    """Quién manda en el marcador y cuándo cambió por última vez.

    Sirve para repartir la decisión del partido según el reglamento: gana el
    lanzador que estaba en el juego cuando su equipo tomó la ventaja definitiva,
    y pierde el que permitió esa carrera.
    """

    leader: str | None = None
    final_change: tuple[str, str, str] | None = None


def simulate_game(
    game_key: str,
    home: TeamGameInput,
    away: TeamGameInput,
    venue: Venue,
    season: SeasonRules,
    rates: LeagueRates,
    seed: int,
    weather: WeatherSample | None = None,
    park: ParkFactors | None = None,
    record_events: bool = True,
) -> GameResult:
    rng = rng_for(seed, "game", game_key)
    park_factors = park or (ParkFactors.compute(venue, weather) if weather else NEUTRAL_PARK)

    home_state = _new_team_state(home, season.designated_hitter)
    away_state = _new_team_state(away, season.designated_hitter)
    events: list[dict] = []

    lead = _LeadTracker()

    inning = 1
    ended_mid_inning_side: str | None = None
    state_final = GameState.FINAL

    while True:
        for half, (batting, fielding) in (
            ("top", (away_state, home_state)),
            ("bottom", (home_state, away_state)),
        ):
            side = "away" if half == "top" else "home"

            # El local no batea en la parte baja de la última entrada si ya gana.
            # No se le añade entrada al line score: no bateó.
            if (
                half == "bottom"
                and inning >= REGULATION_INNINGS
                and home_state.runs > away_state.runs
            ):
                return _finalize(
                    game_key,
                    home,
                    away,
                    venue,
                    season,
                    home_state,
                    away_state,
                    inning,
                    GameState.FINAL,
                    None,
                    lead.final_change,
                    weather,
                    park_factors,
                    seed,
                    events,
                )

            while len(batting.box.line_score) < inning:
                batting.box.line_score.append(0)

            walk_off = _play_half_inning(
                rng=rng,
                inning=inning,
                side=side,
                batting=batting,
                fielding=fielding,
                season=season,
                rates=rates,
                park=park_factors,
                events=events if record_events else None,
                home_state=home_state,
                away_state=away_state,
                lead=lead,
            )

            if walk_off:
                return _finalize(
                    game_key,
                    home,
                    away,
                    venue,
                    season,
                    home_state,
                    away_state,
                    inning,
                    GameState.FINAL,
                    side,
                    lead.final_change,
                    weather,
                    park_factors,
                    seed,
                    events,
                )

            # Regla de nocaut, si la competición la activó.
            if season.mercy_rule_run_diff is not None and inning >= season.mercy_rule_after_inning:
                diff = abs(home_state.runs - away_state.runs)
                if diff >= season.mercy_rule_run_diff and (
                    half == "bottom"
                    or away_state.runs - home_state.runs >= season.mercy_rule_run_diff
                ):
                    return _finalize(
                        game_key,
                        home,
                        away,
                        venue,
                        season,
                        home_state,
                        away_state,
                        inning,
                        GameState.FINAL,
                        None,
                        lead.final_change,
                        weather,
                        park_factors,
                        seed,
                        events,
                    )

        # Fin de la entrada completa: ¿se acabó?
        if inning >= REGULATION_INNINGS and home_state.runs != away_state.runs:
            break
        if inning >= REGULATION_INNINGS and home_state.runs == away_state.runs:
            if not season.extra_innings:
                state_final = GameState.FINAL
                break
            if inning >= MAX_INNINGS:
                state_final = GameState.SUSPENDED
                break
        inning += 1

    return _finalize(
        game_key,
        home,
        away,
        venue,
        season,
        home_state,
        away_state,
        inning,
        state_final,
        ended_mid_inning_side,
        lead.final_change,
        weather,
        park_factors,
        seed,
        events,
    )


def _score_run(
    runner: Runner,
    batting: _TeamState,
    fielding: _TeamState,
    inning: int,
    side: str,
    home_state: _TeamState,
    away_state: _TeamState,
    lead: _LeadTracker,
    rbi_to: BattingLine | None,
) -> None:
    """Anota una carrera y la carga a quien corresponde.

    La carrera se carga al lanzador que puso al corredor en base, no al que
    está en el montículo: así lo hace el reglamento y así cuadra la suma de
    carreras permitidas con el marcador.
    """
    batting.box.line_score[inning - 1] += 1
    batting.batting_lines[runner.person_key].runs += 1
    if rbi_to is not None:
        rbi_to.runs_batted_in += 1

    responsible = fielding.pitching_lines[runner.responsible_pitcher_key]
    responsible.runs_allowed += 1
    if runner.earned:
        responsible.earned_runs += 1

    # ¿Cambió el liderato con esta carrera?
    home_runs, away_runs = home_state.runs, away_state.runs
    if home_runs > away_runs:
        new_leader = "home"
    elif away_runs > home_runs:
        new_leader = "away"
    else:
        new_leader = None
    if new_leader != lead.leader:
        lead.leader = new_leader
        if new_leader is not None:
            scoring_state = home_state if new_leader == "home" else away_state
            lead.final_change = (
                new_leader,
                scoring_state.current_pitcher_key,
                runner.responsible_pitcher_key,
            )


def _maybe_change_pitcher(
    state: _TeamState,
    rng: random.Random,
    inning: int,
    outs: int,
    own_runs: int,
    opponent_runs: int,
    is_final_inning: bool,
    bases_occupied: int,
) -> None:
    """Decisión del manager sobre el montículo. Autónoma, sin intervención.

    No hay magia: se mira el cansancio acumulado, el daño recibido, la entrada
    y el marcador. Si el bullpen se agotó, el lanzador sigue —preferimos un
    brazo quemado a un partido sin terminar.
    """
    line = state.current_pitching_line()
    profile = state.current_profile
    assert profile is not None
    if not state.bullpen_queue and state.closer_key is None:
        return

    lead_margin = own_runs - opponent_runs
    change = False

    if (
        line.pitches >= profile.max_pitches
        or (line.pitches >= profile.max_pitches * 0.82 and bases_occupied > 0)
        or (line.is_starter and line.runs_allowed >= 6 and inning >= 3)
        or (line.is_starter and line.runs_allowed >= 4 and line.pitches > profile.max_pitches * 0.7)
        or (not line.is_starter and line.outs_recorded >= 3 and line.runs_allowed >= 3)
    ):
        change = True

    # Situación de cierre: última entrada, ventaja corta, cerrador disponible.
    closing = (
        is_final_inning
        and 1 <= lead_margin <= 3
        and state.closer_key is not None
        and state.closer_key != state.current_pitcher_key
        and state.closer_key not in state.pitching_lines
    )
    if closing:
        change = True

    if not change:
        return

    if closing:
        next_key = state.closer_key
    elif state.bullpen_queue:
        next_key = state.bullpen_queue.pop(0)
    elif state.closer_key and state.closer_key not in state.pitching_lines:
        next_key = state.closer_key
    else:
        return
    assert next_key is not None

    outgoing = line
    outgoing.hold = bool(
        not outgoing.is_starter
        and 1 <= outgoing.entered_lead <= 3
        and outgoing.outs_recorded >= 1
        and lead_margin > 0
    )

    person = state.roster[next_key]
    new_line = PitchingLine(
        person_key=next_key,
        is_starter=False,
        entered_inning=inning,
        entered_lead=lead_margin,
    )
    state.pitching_lines[next_key] = new_line
    state.box.pitching.append(new_line)
    state.current_pitcher_key = next_key
    state.current_profile = PitcherProfile.of(person, is_starter=False)
    _ensure_fielding_line(state, next_key, str(Position.PITCHER))


def _advance_on_single(
    rng: random.Random, bases: list[Runner | None], batter: Runner, speed: float
) -> list[Runner]:
    """Sencillo: devuelve los corredores que anotan y deja las bases puestas."""
    scored: list[Runner] = []
    third, second, first = bases[2], bases[1], bases[0]
    bases[2] = bases[1] = bases[0] = None
    if third is not None:
        scored.append(third)
    if second is not None:
        # Desde segunda anota con un sencillo la mayoría de las veces.
        if rng.random() < 0.55 + 0.3 * speed:
            scored.append(second)
        else:
            bases[2] = second
    if first is not None:
        if bases[2] is None and rng.random() < 0.22 + 0.25 * speed:
            bases[2] = first
        else:
            bases[1] = first
    bases[0] = batter
    return scored


def _advance_on_double(
    rng: random.Random, bases: list[Runner | None], batter: Runner, speed: float
) -> list[Runner]:
    scored: list[Runner] = []
    third, second, first = bases[2], bases[1], bases[0]
    bases[2] = bases[1] = bases[0] = None
    for runner in (third, second):
        if runner is not None:
            scored.append(runner)
    if first is not None:
        if rng.random() < 0.38 + 0.3 * speed:
            scored.append(first)
        else:
            bases[2] = first
    bases[1] = batter
    return scored


def _walk_forced(bases: list[Runner | None], batter: Runner) -> list[Runner]:
    """Boleto o golpeado: solo avanza quien está forzado."""
    scored: list[Runner] = []
    if bases[0] is None:
        bases[0] = batter
        return scored
    if bases[1] is None:
        bases[1] = bases[0]
        bases[0] = batter
        return scored
    if bases[2] is None:
        bases[2] = bases[1]
        bases[1] = bases[0]
        bases[0] = batter
        return scored
    scored.append(bases[2])
    bases[2] = bases[1]
    bases[1] = bases[0]
    bases[0] = batter
    return scored


def _play_half_inning(
    rng: random.Random,
    inning: int,
    side: str,
    batting: _TeamState,
    fielding: _TeamState,
    season: SeasonRules,
    rates: LeagueRates,
    park: ParkFactors,
    events: list[dict] | None,
    home_state: _TeamState,
    away_state: _TeamState,
    lead: _LeadTracker,
) -> bool:
    """Juega media entrada. Devuelve True si el partido acabó por walk-off."""
    outs = 0
    bases: list[Runner | None] = [None, None, None]
    is_home_batting = side == "home"

    # Corredor automático en entradas extra: su carrera no es limpia.
    if inning >= AUTOMATIC_RUNNER_FROM_INNING and season.extra_innings:
        previous_slot = (batting.lineup_index - 1) % len(batting.setup.batting_order)
        bases[1] = Runner(
            person_key=batting.setup.batting_order[previous_slot],
            responsible_pitcher_key=fielding.current_pitcher_key,
            earned=False,
        )

    # Una vez que hay un error en la entrada, los corredores que lleguen
    # después se cuentan como sucios: sin el error, la entrada probablemente ya
    # habría terminado. Es una aproximación declarada del reglamento de
    # anotación, que exige reconstruir la entrada "como debió ser".
    error_this_inning = False
    plate_appearances = 0
    while outs < 3:
        plate_appearances += 1
        if plate_appearances > 120:
            raise InvariantViolation(
                f"media entrada sin cerrar tras 120 turnos al bate "
                f"(entrada {inning}, {side}): el motor no está registrando outs"
            )
        _maybe_change_pitcher(
            state=fielding,
            rng=rng,
            inning=inning,
            outs=outs,
            own_runs=fielding.runs,
            opponent_runs=batting.runs,
            is_final_inning=inning >= REGULATION_INNINGS,
            bases_occupied=sum(1 for b in bases if b is not None),
        )

        batter_key = batting.setup.batting_order[batting.lineup_index]
        batting.lineup_index = (batting.lineup_index + 1) % len(batting.setup.batting_order)
        if batting.lineup_index == 0:
            batting.times_through_order += 1

        batter = batting.batters[batter_key]
        bat_line = batting.batting_lines[batter_key]
        pitcher_profile = fielding.current_profile
        assert pitcher_profile is not None
        pitch_line = fielding.current_pitching_line()

        # --- Intento de robo antes del turno ---------------------------------
        if bases[0] is not None and bases[1] is None and outs < 3:
            runner_key = bases[0].person_key
            runner = batting.roster.get(runner_key)
            if runner is not None:
                runner_speed = runner.batting.speed
                catcher_arm = _catcher_arm(fielding)
                attempt_chance = max(
                    0.0, 0.035 + 0.22 * runner_speed - 0.10 * pitcher_profile.hold_runners
                )
                if rng.random() < attempt_chance:
                    success = 0.52 + 0.34 * (runner_speed - catcher_arm)
                    if rng.random() < max(0.25, min(0.92, success)):
                        bases[1] = bases[0]
                        bases[0] = None
                        batting.batting_lines[runner_key].stolen_bases += 1
                    else:
                        bases[0] = None
                        batting.batting_lines[runner_key].caught_stealing += 1
                        outs += 1
                        pitch_line.outs_recorded += 1
                        batting.box.outs_suffered += 1
                        catcher_key, catcher_pos = _catcher_of(fielding)
                        _ensure_fielding_line(fielding, catcher_key, catcher_pos).assists += 1
                        tagger_key, tagger_pos = _fielder_for(fielding, rng, is_fly=False)
                        _ensure_fielding_line(fielding, tagger_key, tagger_pos).putouts += 1
                        if outs >= 3:
                            break

        # --- Resolución del turno al bate ------------------------------------
        fatigue = _fatigue_penalty(pitch_line, pitcher_profile)
        # Penalización por vueltas al orden: el bateador ya lo vio hoy.
        order_penalty = min(0.12, 0.04 * batting.times_through_order)
        probabilities = plate_probabilities(
            batter=batter,
            pitcher=pitcher_profile,
            rates=rates,
            fatigue_penalty=min(1.0, fatigue + order_penalty),
            hr_park_factor=park.homerun,
            xbh_park_factor=park.extra_base,
        )
        outcome = resolve_plate_appearance(rng.random(), probabilities)

        pitches = int(round(_PITCHES_BY_OUTCOME[outcome] + rng.uniform(-1.0, 1.4)))
        pitch_line.pitches += max(1, pitches)
        pitch_line.batters_faced += 1
        bat_line.plate_appearances += 1

        scored: list[Runner] = []
        rbi_line: BattingLine | None = bat_line

        earned = not error_this_inning
        if outcome == WALK:
            bat_line.walks += 1
            pitch_line.walks += 1
            scored = _walk_forced(
                bases, Runner(batter_key, fielding.current_pitcher_key, earned=earned)
            )
        elif outcome == HIT_BY_PITCH:
            bat_line.hit_by_pitch += 1
            pitch_line.hit_batsmen += 1
            scored = _walk_forced(
                bases, Runner(batter_key, fielding.current_pitcher_key, earned=earned)
            )
        elif outcome == STRIKEOUT:
            bat_line.at_bats += 1
            bat_line.strikeouts += 1
            pitch_line.strikeouts += 1
            pitch_line.outs_recorded += 1
            batting.box.outs_suffered += 1
            outs += 1
            catcher_key, catcher_pos = _catcher_of(fielding)
            _ensure_fielding_line(fielding, catcher_key, catcher_pos).putouts += 1
            rbi_line = None
        elif outcome == HOMERUN:
            bat_line.at_bats += 1
            bat_line.hits += 1
            bat_line.home_runs += 1
            pitch_line.hits_allowed += 1
            pitch_line.home_runs_allowed += 1
            for base_index in (2, 1, 0):
                runner = bases[base_index]
                if runner is not None:
                    scored.append(runner)
                    bases[base_index] = None
            scored.append(Runner(batter_key, fielding.current_pitcher_key, earned=earned))
        elif outcome == TRIPLE:
            bat_line.at_bats += 1
            bat_line.hits += 1
            bat_line.triples += 1
            pitch_line.hits_allowed += 1
            for base_index in (2, 1, 0):
                runner = bases[base_index]
                if runner is not None:
                    scored.append(runner)
                    bases[base_index] = None
            bases[2] = Runner(batter_key, fielding.current_pitcher_key, earned=earned)
        elif outcome == DOUBLE:
            bat_line.at_bats += 1
            bat_line.hits += 1
            bat_line.doubles += 1
            pitch_line.hits_allowed += 1
            scored = _advance_on_double(
                rng,
                bases,
                Runner(batter_key, fielding.current_pitcher_key, earned=earned),
                batter.speed,
            )
        elif outcome == SINGLE:
            bat_line.at_bats += 1
            bat_line.hits += 1
            bat_line.singles += 1
            pitch_line.hits_allowed += 1
            scored = _advance_on_single(
                rng,
                bases,
                Runner(batter_key, fielding.current_pitcher_key, earned=earned),
                batter.speed,
            )
        else:
            scored, rbi_line, added_outs, had_error = _resolve_ball_in_play(
                rng=rng,
                bases=bases,
                batter_key=batter_key,
                batter=batter,
                bat_line=bat_line,
                batting=batting,
                fielding=fielding,
                rates=rates,
                outs=outs,
                error_this_inning=error_this_inning,
            )
            error_this_inning = error_this_inning or had_error
            outs += added_outs
            pitch_line.outs_recorded += added_outs
            batting.box.outs_suffered += added_outs

        for runner in scored:
            _score_run(
                runner=runner,
                batting=batting,
                fielding=fielding,
                inning=inning,
                side=side,
                home_state=home_state,
                away_state=away_state,
                lead=lead,
                rbi_to=rbi_line,
            )

        if events is not None:
            events.append(
                {
                    "inning": inning,
                    "half": "bottom" if is_home_batting else "top",
                    "outs": outs,
                    "batter": batter_key,
                    "pitcher": fielding.current_pitcher_key,
                    "outcome": _OUTCOME_NAMES[outcome],
                    "runs": len(scored),
                    "home_score": home_state.runs,
                    "away_score": away_state.runs,
                }
            )

        # Walk-off: el local toma la ventaja en la parte baja de la novena o
        # más allá y el partido se detiene ahí mismo, con la entrada abierta.
        if is_home_batting and inning >= REGULATION_INNINGS and home_state.runs > away_state.runs:
            _strand_runners(batting, bases)
            return True

    _strand_runners(batting, bases)
    return False


def _strand_runners(batting: _TeamState, bases: list[Runner | None]) -> None:
    stranded = sum(1 for b in bases if b is not None)
    batting.box.left_on_base += stranded


def _catcher_of(state: _TeamState) -> tuple[str, str]:
    for key, position in state.setup.positions.items():
        if position == str(Position.CATCHER):
            return key, position
    return state.current_pitcher_key, str(Position.PITCHER)


def _catcher_arm(state: _TeamState) -> float:
    key, _ = _catcher_of(state)
    person = state.roster.get(key)
    return person.fielding.arm if person else 0.5


def _resolve_ball_in_play(
    rng: random.Random,
    bases: list[Runner | None],
    batter_key: str,
    batter: BatterProfile,
    bat_line: BattingLine,
    batting: _TeamState,
    fielding: _TeamState,
    rates: LeagueRates,
    outs: int,
    error_this_inning: bool = False,
) -> tuple[list[Runner], BattingLine | None, int, bool]:
    """Pelota puesta en juego que no fue hit limpio.

    Aquí viven el error de fildeo, la doble matanza y el elevado de sacrificio.
    El error importa: pone al bateador en base sin hit y la carrera que anote
    ese corredor es **sucia**, lo que mantiene ER <= R en la línea del lanzador.
    """
    is_fly = rng.random() < batter.fly_ball_rate
    fielder_key, fielder_position = _fielder_for(fielding, rng, is_fly)
    fielder = fielding.roster.get(fielder_key)
    hands = fielder.fielding.hands if fielder else 0.5

    error_chance = max(0.002, rates.error_rate * (1.6 - hands))
    if rng.random() < error_chance:
        _ensure_fielding_line(fielding, fielder_key, fielder_position).errors += 1
        bat_line.at_bats += 1
        bat_line.reached_on_error += 1
        scored = _advance_on_single(
            rng,
            bases,
            Runner(batter_key, fielding.current_pitcher_key, earned=False),
            batter.speed,
        )
        # Quien ya estaba en base antes del error conserva su condición: su
        # carrera sigue siendo limpia. El que llega por el error, y los que
        # lleguen después en esta entrada, son sucios.
        return scored, None, 0, True

    # Elevado de sacrificio: corredor en tercera, menos de dos outs, elevado.
    if is_fly and bases[2] is not None and outs < 2 and rng.random() < 0.34:
        runner = bases[2]
        bases[2] = None
        bat_line.sac_flies += 1
        _ensure_fielding_line(fielding, fielder_key, fielder_position).putouts += 1
        assert runner is not None
        return [runner], bat_line, 1, False

    bat_line.at_bats += 1

    # Doble matanza: corredor en primera, menos de dos outs, roletazo.
    if not is_fly and bases[0] is not None and outs < 2:
        turn_chance = 0.33 + 0.12 * (1.0 - batter.speed) + 0.1 * rates.professionalization
        if rng.random() < turn_chance:
            lead_runner = bases[0]
            bases[0] = None
            assert lead_runner is not None
            batting.batting_lines[lead_runner.person_key].left_on_base += 0
            pivot_key, pivot_position = _fielder_for(fielding, rng, is_fly=False)
            _ensure_fielding_line(fielding, pivot_key, pivot_position).putouts += 1
            _ensure_fielding_line(fielding, fielder_key, fielder_position).assists += 1
            first_key, first_position = _fielder_for(fielding, rng, is_fly=False)
            _ensure_fielding_line(fielding, first_key, first_position).putouts += 1
            return [], None, 2, False

    _ensure_fielding_line(fielding, fielder_key, fielder_position).putouts += 1

    # Out que produce: roletazo que mueve al corredor de segunda a tercera.
    scored: list[Runner] = []
    if not is_fly and bases[1] is not None and bases[2] is None and rng.random() < 0.22:
        bases[2] = bases[1]
        bases[1] = None
    elif is_fly and bases[2] is not None and outs < 2 and rng.random() < 0.05:
        runner = bases[2]
        bases[2] = None
        assert runner is not None
        scored.append(runner)
        return scored, bat_line, 1, False

    return scored, None, 1, False


_OUTCOME_NAMES = {
    OUT_IN_PLAY: "out_en_juego",
    SINGLE: "sencillo",
    DOUBLE: "doble",
    TRIPLE: "triple",
    HOMERUN: "jonron",
    WALK: "boleto",
    HIT_BY_PITCH: "golpeado",
    STRIKEOUT: "ponche",
}


def _most_effective_reliever(state: _TeamState) -> PitchingLine | None:
    relievers = [line for line in state.box.pitching if not line.is_starter]
    if not relievers:
        return None
    return max(relievers, key=lambda line: (line.outs_recorded, -line.earned_runs))


def _assign_decisions(
    home_state: _TeamState,
    away_state: _TeamState,
    final_change: tuple[str, str, str] | None,
    innings_played: int,
) -> None:
    """Reparte victoria, derrota, salvamento y hold.

    Reglas implementadas: el ganador es el lanzador que estaba en el juego
    cuando su equipo tomó la ventaja definitiva; si es el abridor y no completó
    5 entradas en un partido de duración reglamentaria, la victoria pasa al
    relevista más efectivo, como manda el reglamento. El perdedor es quien
    permitió la carrera de esa ventaja.
    """
    if home_state.runs == away_state.runs or final_change is None:
        return

    winner_side, credited_key, blamed_key = final_change
    winner = home_state if winner_side == "home" else away_state
    loser = away_state if winner_side == "home" else home_state

    win_line = winner.pitching_lines.get(credited_key)
    if win_line is None:
        win_line = winner.box.pitching[0]
    if win_line.is_starter and win_line.outs_recorded < 15 and innings_played >= REGULATION_INNINGS:
        alternative = _most_effective_reliever(winner)
        if alternative is not None:
            win_line = alternative
    win_line.win = True
    win_line.hold = False

    loss_line = loser.pitching_lines.get(blamed_key)
    if loss_line is None:
        loss_line = loser.box.pitching[0]
    loss_line.loss = True
    loss_line.hold = False

    finisher = winner.box.pitching[-1]
    if (
        finisher is not win_line
        and finisher.outs_recorded >= 1
        and finisher.entered_lead > 0
        and (finisher.entered_lead <= 3 or finisher.outs_recorded >= 9)
    ):
        finisher.save = True
        finisher.hold = False
    elif finisher is not win_line:
        finisher.hold = False


def _finalize(
    game_key: str,
    home: TeamGameInput,
    away: TeamGameInput,
    venue: Venue,
    season: SeasonRules,
    home_state: _TeamState,
    away_state: _TeamState,
    innings_played: int,
    state: GameState,
    ended_mid_inning_side: str | None,
    final_change: tuple[str, str, str] | None,
    weather: WeatherSample | None,
    park: ParkFactors,
    seed: int,
    events: list[dict],
) -> GameResult:
    _assign_decisions(home_state, away_state, final_change, innings_played)

    # `outs_suffered` se contó turno a turno; no se recalcula aquí a propósito,
    # para que la invariante de outs compare dos cuentas independientes.
    for team_state in (home_state, away_state):
        team_state.box.batting.sort(key=lambda line: line.lineup_slot)

    result = GameResult(
        game_key=game_key,
        home_club_key=home.club.key,
        away_club_key=away.club.key,
        venue_key=venue.key,
        state=state,
        innings_played=innings_played,
        home_score=home_state.runs,
        away_score=away_state.runs,
        home_box=home_state.box,
        away_box=away_state.box,
        allows_tie=season.allow_ties or state is GameState.SUSPENDED,
        ended_mid_inning_side=ended_mid_inning_side,
        weather=(
            {
                "temperature_c": weather.temperature_c,
                "humidity": weather.humidity,
                "wind_kph": weather.wind_kph,
                "precipitation_mm": weather.precipitation_mm,
                "model": weather.model,
            }
            if weather
            else {"model": "none"}
        ),
        park_note=park.wind_note,
        seed=seed,
        engine_version=ENGINE_VERSION,
        events=events,
    )
    check_game_result(result)
    _check_fielding_consistency(result)
    return result


def _check_fielding_consistency(result: GameResult) -> None:
    """Cada out tiene exactamente un putout. Si no, la defensa no cuadra."""
    for side in ("home", "away"):
        box = result.box_for(side)
        opposing = result.box_for("away" if side == "home" else "home")
        outs = sum(line.outs_recorded for line in box.pitching)
        putouts = sum(line.putouts for line in box.fielding)
        if outs != putouts:
            raise InvariantViolation(
                f"{side}: {outs} outs registrados pero {putouts} putouts anotados"
            )
        if box.errors and not any(line.reached_on_error for line in opposing.batting):
            raise InvariantViolation(
                f"{side}: hay errores anotados pero nadie llegó a base por error"
            )
