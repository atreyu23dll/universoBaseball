"""Previsualización del calendario y del cuadro, para el asistente.

El paso del calendario del asistente pide seis números —partidos objetivo,
partidos por serie, días entre series, días de descanso, vueltas dentro de la
división y vueltas fuera— y hasta ahora el usuario no veía lo que producían
hasta generar la competición. Con seis controles que se multiplican entre sí,
eso es pedirle que haga la cuenta de cabeza.

Este servicio responde a «¿y si pongo esto?» con **el mismo motor** que
construirá el calendario de verdad (`build_schedule`, `assign_groups`,
`PlayoffRules`), así que lo que se dibuja no es una maqueta: es el calendario.
No escribe nada y no necesita que la competición exista.

Los clubes son marcadores —«Club 1», «Club 2»— porque en este paso todavía no
existen: el usuario está decidiendo las reglas, y quién va a cada división lo
decidirá el generador por cercanía cuando los clubes tengan sede.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.application.errors import ValidationFailure
from simulation.competitions.groups import group_sizes
from simulation.competitions.playoffs import PlayoffSeries, seed_bracket
from simulation.competitions.ruleset import (
    PlayoffFormat,
    PlayoffRules,
    StructureRules,
)
from simulation.competitions.schedule import build_schedule
from simulation.core.errors import RuleValidationError, ScheduleError

#: Tope de clubes de la previsualización. Es el mismo del reglamento.
MAX_CLUBS = 64


def preview_schedule(payload: dict) -> dict:
    """Calendario, cruces y cuadro que saldrían de estos parámetros."""
    try:
        club_count = int(payload.get("club_count", 0))
        structure = StructureRules.model_validate(payload.get("structure") or {})
        playoffs = PlayoffRules.model_validate(
            payload.get("playoffs") or {"slots": 0, "format": "none", "round_lengths": []}
        )
    except (ValueError, TypeError) as exc:
        raise ValidationFailure(f"los parámetros del calendario no son válidos: {exc}") from exc

    if not 2 <= club_count <= MAX_CLUBS:
        raise ValidationFailure(
            f"la previsualización necesita entre 2 y {MAX_CLUBS} clubes; se pidieron {club_count}"
        )

    season = payload.get("season") or {}
    games_target = int(season.get("games_per_club_target", 20))
    games_per_series = int(season.get("games_per_series", 1))
    days_between = int(season.get("days_between_series", 0))
    rest_days = [int(d) for d in season.get("rest_days_weekday", [0])]
    start = _parse_date(season.get("start_date"))

    etiquetas, grupo_de = _fake_groups(club_count, structure)
    club_keys = [f"c{i + 1:02d}" for i in range(club_count)]

    try:
        informe = build_schedule(
            club_keys=club_keys,
            games_per_club_target=games_target,
            start_date=start,
            rest_days_weekday=rest_days,
            games_per_series=games_per_series,
            days_between_series=days_between,
            groups=grupo_de if structure.has_groups else None,
            intra_cycles=structure.intra_cycles,
            inter_cycles=structure.inter_cycles,
        )
    except ScheduleError as exc:
        return {
            "ok": False,
            "error": exc.message,
            "suggestions": list(exc.suggestions),
            "structure": _structure_view(structure, etiquetas, grupo_de, club_count),
            "playoffs": _bracket_view(playoffs, structure, etiquetas),
        }

    cruces: dict[str, dict[str, int]] = {clave: {} for clave in club_keys}
    por_tipo = {"intra": 0, "inter": 0, "single": 0}
    en_casa = dict.fromkeys(club_keys, 0)
    por_fecha: dict[str, int] = {}
    for juego in informe.games:
        cruces[juego.home_key][juego.away_key] = cruces[juego.home_key].get(juego.away_key, 0) + 1
        cruces[juego.away_key][juego.home_key] = cruces[juego.away_key].get(juego.home_key, 0) + 1
        por_tipo[juego.matchup] += 1
        en_casa[juego.home_key] += 1
        clave = juego.game_date.isoformat()
        por_fecha[clave] = por_fecha.get(clave, 0) + 1

    intra_por_club, inter_por_club = _split_by_club(informe, club_keys, grupo_de, structure)
    jugados = sorted(informe.games_by_club.values())

    return {
        "ok": True,
        "clubs": [
            {
                "key": clave,
                "label": f"Club {indice + 1}",
                "group": grupo_de.get(clave, ""),
                "games": informe.games_by_club.get(clave, 0),
                "intra_games": intra_por_club.get(clave, 0),
                "inter_games": inter_por_club.get(clave, 0),
                "home_games": en_casa.get(clave, 0),
            }
            for indice, clave in enumerate(club_keys)
        ],
        "totals": {
            "games": len(informe.games),
            "rounds": informe.rounds,
            "games_per_club_min": jugados[0] if jugados else 0,
            "games_per_club_max": jugados[-1] if jugados else 0,
            "requested_games_per_club": informe.requested_games_per_club,
            "adjusted": informe.adjusted,
            "intra_games": por_tipo["intra"],
            "inter_games": por_tipo["inter"],
            "first_date": informe.first_date.isoformat() if informe.first_date else None,
            "last_date": informe.last_date.isoformat() if informe.last_date else None,
            "calendar_days": (
                (informe.last_date - informe.first_date).days + 1
                if informe.first_date and informe.last_date
                else 0
            ),
            "playing_days": len(por_fecha),
            "max_games_in_a_day": max(por_fecha.values()) if por_fecha else 0,
        },
        # Matriz de cruces: cuántas veces juega cada club contra cada otro. Es
        # lo que hace visible la asimetría de las divisiones.
        "matchups": cruces,
        # Las dos primeras semanas, día a día: aclara de un vistazo qué hacen
        # los días de descanso y los días entre series.
        "first_dates": _calendar_strip(informe, por_fecha, rest_days),
        "warnings": list(informe.warnings),
        "structure": _structure_view(structure, etiquetas, grupo_de, club_count),
        "playoffs": _bracket_view(playoffs, structure, etiquetas),
    }


def _parse_date(value: object) -> date:
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError as exc:
            raise ValidationFailure(f"fecha de inicio inválida: {value}") from exc
    return date(2042, 3, 20)


def _fake_groups(club_count: int, structure: StructureRules) -> tuple[list[str], dict[str, str]]:
    """Reparte los clubes marcadores entre las divisiones, por plazas.

    No se usa `assign_groups` porque el reparto real es geográfico y aquí los
    clubes no tienen sede todavía. Lo que importa en este paso es **cuántos**
    caen en cada división, que es lo que decide el calendario.
    """
    etiquetas = structure.labels
    if not structure.has_groups:
        return etiquetas, {f"c{i + 1:02d}": etiquetas[0] for i in range(club_count)}

    plazas = group_sizes(structure, club_count)
    grupo_de: dict[str, str] = {}
    indice = 0
    for etiqueta, cupo in zip(etiquetas, plazas, strict=True):
        for _ in range(cupo):
            if indice >= club_count:
                break
            grupo_de[f"c{indice + 1:02d}"] = etiqueta
            indice += 1
    # Si las plazas declaradas no llegan a los clubes, el resto cae en la
    # última división: el reglamento ya lo rechazará, pero la previsualización
    # tiene que poder dibujar el caso para que se vea el desajuste.
    while indice < club_count:
        grupo_de[f"c{indice + 1:02d}"] = etiquetas[-1]
        indice += 1
    return etiquetas, grupo_de


def _split_by_club(
    informe, club_keys: list[str], grupo_de: dict[str, str], structure: StructureRules
) -> tuple[dict[str, int], dict[str, int]]:
    intra = dict.fromkeys(club_keys, 0)
    inter = dict.fromkeys(club_keys, 0)
    if not structure.has_groups:
        return intra, inter
    for juego in informe.games:
        destino = intra if juego.matchup == "intra" else inter
        destino[juego.home_key] += 1
        destino[juego.away_key] += 1
    return intra, inter


def _calendar_strip(informe, por_fecha: dict[str, int], rest_days: list[int]) -> list[dict]:
    """Los primeros catorce días del calendario, jueguen o no."""
    if informe.first_date is None:
        return []
    salida: list[dict] = []
    for desplazamiento in range(14):
        dia = informe.first_date + timedelta(days=desplazamiento)
        clave = dia.isoformat()
        salida.append(
            {
                "date": clave,
                "weekday": dia.weekday(),
                "games": por_fecha.get(clave, 0),
                "rest_day": dia.weekday() in set(rest_days),
            }
        )
    return salida


def _structure_view(
    structure: StructureRules,
    etiquetas: list[str],
    grupo_de: dict[str, str],
    club_count: int,
) -> dict:
    cuenta: dict[str, int] = dict.fromkeys(etiquetas, 0)
    for etiqueta in grupo_de.values():
        cuenta[etiqueta] = cuenta.get(etiqueta, 0) + 1
    return {
        "has_groups": structure.has_groups,
        "count": structure.count,
        "assignment": str(structure.assignment),
        "intra_cycles": structure.intra_cycles,
        "inter_cycles": structure.inter_cycles,
        "qualifiers_per_group": structure.qualifiers_per_group,
        "wildcards": structure.wildcards,
        "playoff_slots": structure.playoff_slots if structure.has_groups else None,
        "groups": [{"label": etiqueta, "clubs": cuenta.get(etiqueta, 0)} for etiqueta in etiquetas],
        "undersized": [
            etiqueta for etiqueta, cuantos in cuenta.items() if structure.has_groups and cuantos < 2
        ],
    }


def _bracket_view(playoffs: PlayoffRules, structure: StructureRules, etiquetas: list[str]) -> dict:
    """El cuadro que saldría: quién entra por división, quién por repechaje.

    Las siembras son las posiciones, no clubes: en este paso nadie ha jugado
    todavía. Lo que se ve es la **forma** del cuadro —cuántas series por ronda,
    quién tiene pase directo y de dónde sale cada clasificado—, que es
    exactamente lo que no se entendía leyendo dos números sueltos.
    """
    if playoffs.format is PlayoffFormat.NONE or playoffs.slots < 2:
        return {
            "format": str(playoffs.format),
            "slots": 0,
            "note": "sin postemporada: el campeón sale de la tabla",
            "qualifiers": [],
            "rounds": [],
        }

    clasificados: list[dict] = []
    if structure.has_groups:
        for puesto in range(structure.qualifiers_per_group):
            for etiqueta in etiquetas:
                clasificados.append(
                    {
                        "seed": len(clasificados) + 1,
                        "route": "group_winner",
                        "label": f"{puesto + 1}.º de {etiqueta}",
                        "group": etiqueta,
                    }
                )
        for numero in range(structure.wildcards):
            clasificados.append(
                {
                    "seed": len(clasificados) + 1,
                    "route": "wildcard",
                    "label": f"Repechaje {numero + 1}",
                    "group": "",
                }
            )
    else:
        for puesto in range(playoffs.slots):
            clasificados.append(
                {
                    "seed": puesto + 1,
                    "route": "overall",
                    "label": f"{puesto + 1}.º de la tabla",
                    "group": "",
                }
            )
    clasificados = clasificados[: playoffs.slots]

    etiquetas_siembra = [c["label"] for c in clasificados]
    try:
        primera, byes = seed_bracket([f"s{i}" for i in range(len(clasificados))], playoffs)
    except RuleValidationError as exc:
        return {
            "format": str(playoffs.format),
            "slots": playoffs.slots,
            "note": exc.message,
            "qualifiers": clasificados,
            "rounds": [],
        }

    def nombre(clave: str) -> str:
        return etiquetas_siembra[int(clave[1:])]

    rondas: list[dict] = [
        {
            "round": 1,
            "best_of": primera[0].best_of if primera else 1,
            "byes": [nombre(clave) for clave in byes],
            "series": [{"high": nombre(s.high_seed), "low": nombre(s.low_seed)} for s in primera],
        }
    ]
    # Las rondas siguientes se describen por su tamaño: quién llega a ellas
    # depende de lo que pase en el campo.
    vivos = len(primera) + len(byes)
    indice = 1
    while vivos > 1:
        series = vivos // 2
        rondas.append(
            {
                "round": indice + 1,
                "best_of": (
                    playoffs.round_lengths[indice]
                    if indice < len(playoffs.round_lengths)
                    else rondas[-1]["best_of"]
                ),
                "byes": [],
                "series": [{"high": "ganador", "low": "ganador"} for _ in range(series)],
            }
        )
        vivos = series
        indice += 1

    return {
        "format": str(playoffs.format),
        "slots": playoffs.slots,
        "bracket_size": playoffs.bracket_size,
        "byes": playoffs.byes,
        "rounds_needed": playoffs.rounds,
        "declared_rounds": len(playoffs.round_lengths),
        "note": (
            f"{playoffs.slots} clasificados en un cuadro de {playoffs.bracket_size}: "
            f"{playoffs.byes} pase(s) directo(s) a la segunda ronda"
            if playoffs.byes
            else f"cuadro exacto de {playoffs.slots}"
        ),
        "qualifiers": clasificados,
        "rounds": rondas,
    }


def playoff_series_preview(series: list[PlayoffSeries]) -> list[dict]:
    """Serialización menuda de unas series, para pruebas y depuración."""
    return [
        {"key": s.series_key, "round": s.round_index, "high": s.high_seed, "low": s.low_seed}
        for s in series
    ]
