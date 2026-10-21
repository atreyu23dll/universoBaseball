"""Invariantes del motor.

Se comprueban después de cada partido. Si algo de aquí falla, el motor produjo
un estado imposible y preferimos reventar a guardar un box score que no cuadra.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from simulation.core.errors import InvariantViolation

if TYPE_CHECKING:
    from simulation.baseball.result import GameResult


def check_game_result(result: GameResult) -> None:
    """Valida que el box score cierre contra el marcador y las reglas."""
    _check_runs_match_box_score(result)
    _check_outs(result)
    _check_batting_lines(result)
    _check_pitching_lines(result)
    _check_decisions(result)


def _check_runs_match_box_score(result: GameResult) -> None:
    for side, score in (("home", result.home_score), ("away", result.away_score)):
        box = result.box_for(side)
        batting_runs = sum(line.runs for line in box.batting)
        if batting_runs != score:
            raise InvariantViolation(
                f"{side}: carreras del marcador ({score}) != suma de carreras "
                f"anotadas por bateadores ({batting_runs})"
            )
        line_runs = sum(result.line_score_for(side))
        if line_runs != score:
            raise InvariantViolation(
                f"{side}: marcador ({score}) != suma por entradas ({line_runs})"
            )
        opposing = result.box_for("away" if side == "home" else "home")
        runs_allowed = sum(line.runs_allowed for line in opposing.pitching)
        if runs_allowed != score:
            raise InvariantViolation(
                f"{side}: carreras anotadas ({score}) != carreras permitidas por "
                f"los lanzadores rivales ({runs_allowed})"
            )
    if result.home_score == result.away_score and not result.allows_tie:
        raise InvariantViolation("partido terminado en empate sin regla que lo permita")


def _check_outs(result: GameResult) -> None:
    for side in ("home", "away"):
        box = result.box_for(side)
        opposing = result.box_for("away" if side == "home" else "home")
        outs_made = sum(line.outs_recorded for line in opposing.pitching)
        outs_suffered = box.outs_suffered
        if outs_made != outs_suffered:
            raise InvariantViolation(
                f"{side}: outs registrados por los lanzadores rivales ({outs_made}) "
                f"!= outs sufridos ({outs_suffered})"
            )
        if outs_suffered % 3 != 0 and not result.side_stranded_mid_inning(side):
            raise InvariantViolation(
                f"{side}: {outs_suffered} outs no es múltiplo de 3 y la entrada no "
                "quedó abierta por walk-off ni por final de partido"
            )


def _check_batting_lines(result: GameResult) -> None:
    for side in ("home", "away"):
        box = result.box_for(side)
        for line in box.batting:
            hits = line.singles + line.doubles + line.triples + line.home_runs
            if hits != line.hits:
                raise InvariantViolation(
                    f"{line.person_key}: hits ({line.hits}) != 1B+2B+3B+HR ({hits})"
                )
            if line.at_bats < line.hits:
                raise InvariantViolation(
                    f"{line.person_key}: más hits ({line.hits}) que turnos al bate ({line.at_bats})"
                )
            # PA = AB + BB + HBP + sacrificios. El motor no genera sacrificios de
            # toque todavía, pero el elevado de sacrificio sí cuenta fuera de AB.
            expected_pa = line.at_bats + line.walks + line.hit_by_pitch + line.sac_flies
            if expected_pa != line.plate_appearances:
                raise InvariantViolation(
                    f"{line.person_key}: PA ({line.plate_appearances}) != "
                    f"AB+BB+HBP+SF ({expected_pa})"
                )
            if line.strikeouts > line.at_bats:
                raise InvariantViolation(
                    f"{line.person_key}: más ponches ({line.strikeouts}) que AB"
                )


def _check_pitching_lines(result: GameResult) -> None:
    for side in ("home", "away"):
        for line in result.box_for(side).pitching:
            if line.earned_runs > line.runs_allowed:
                raise InvariantViolation(
                    f"{line.person_key}: carreras limpias ({line.earned_runs}) > "
                    f"carreras permitidas ({line.runs_allowed})"
                )
            if line.outs_recorded < 0:
                raise InvariantViolation(f"{line.person_key}: outs negativos")
            if line.strikeouts > line.batters_faced:
                raise InvariantViolation(
                    f"{line.person_key}: más ponches que bateadores enfrentados"
                )


def _check_decisions(result: GameResult) -> None:
    """Un partido decidido tiene exactamente un ganador y un perdedor."""
    wins = [line for side in ("home", "away") for line in result.box_for(side).pitching if line.win]
    losses = [
        line for side in ("home", "away") for line in result.box_for(side).pitching if line.loss
    ]
    if result.home_score != result.away_score:
        if len(wins) != 1:
            raise InvariantViolation(f"se esperaba 1 lanzador ganador, hay {len(wins)}")
        if len(losses) != 1:
            raise InvariantViolation(f"se esperaba 1 lanzador perdedor, hay {len(losses)}")
    elif wins or losses:
        raise InvariantViolation("un empate no reparte decisiones de lanzador")
    saves = [
        line for side in ("home", "away") for line in result.box_for(side).pitching if line.save
    ]
    if len(saves) > 1:
        raise InvariantViolation("no puede haber más de un salvamento por partido")
    if saves and wins and saves[0].person_key == wins[0].person_key:
        raise InvariantViolation("el lanzador ganador no puede acreditarse el salvamento")
