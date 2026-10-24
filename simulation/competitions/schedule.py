"""Construcción de calendario.

Dos formas, según si la competición tiene grupos:

- **Tabla única**: método del círculo (round-robin balanceado) repetido en
  ciclos, alternando localías entre ciclos para que el reparto de casa y visita
  quede equilibrado.
- **Con grupos, divisiones o conferencias**: el calendario deja de ser
  uniforme a propósito. Cada club juega más veces contra los de su grupo
  (`intra_cycles`) que contra los demás (`inter_cycles`), que es justamente el
  sentido de tener divisiones. Los emparejamientos se reparten en jornadas con
  un empaquetado voraz que prioriza a los clubes a los que les quedan más
  partidos, para no dejar jornadas casi vacías al final. Si las vueltas dentro
  y fuera del grupo coinciden, el calendario es un round-robin normal y se
  construye por el camino de siempre.

El empaquetado voraz usa entre un 10 % y un 25 % más de jornadas que el mínimo
teórico (el grado máximo del multigrafo). Es un calendario válido y con las
localías repartidas; lo que cuesta son algunos días de más de temporada, no la
equidad. Un coloreado de aristas óptimo lo arreglaría y no está implementado.

Si un objetivo independiente de partidos no es alcanzable con un número entero
de ciclos, **no se altera la regla en silencio**: se elige el valor factible más
cercano y se devuelve una advertencia explícita. En el editor por fases el
valor se deriva de las vueltas declaradas, por lo que no se lo compara consigo
mismo ni se muestra como una decisión separada.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from simulation.core.errors import ScheduleError


@dataclass(frozen=True)
class ScheduledGame:
    round_index: int
    series_index: int
    game_in_series: int
    home_key: str
    away_key: str
    game_date: date
    #: `intra` si los dos clubes son del mismo grupo, `inter` si no, `single`
    #: cuando la competición no tiene grupos.
    matchup: str = "single"


@dataclass
class ScheduleReport:
    games: list[ScheduledGame]
    games_per_club: int
    requested_games_per_club: int
    rounds: int
    warnings: list[str] = field(default_factory=list)
    first_date: date | None = None
    last_date: date | None = None
    #: Partidos de cada club. Con grupos de tamaños distintos no es el mismo
    #: número para todos, y eso se dice en vez de promediarlo.
    games_by_club: dict[str, int] = field(default_factory=dict)

    @property
    def adjusted(self) -> bool:
        return self.games_per_club != self.requested_games_per_club


def _circle_pairings(keys: list[str]) -> list[list[tuple[str, str]]]:
    """Devuelve n-1 jornadas donde cada equipo juega una vez por jornada."""
    teams = list(keys)
    bye: str | None = None
    if len(teams) % 2 == 1:
        bye = "__BYE__"
        teams.append(bye)

    half = len(teams) // 2
    rounds: list[list[tuple[str, str]]] = []
    rotation = list(teams)
    for _ in range(len(teams) - 1):
        pairs: list[tuple[str, str]] = []
        for i in range(half):
            a, b = rotation[i], rotation[-1 - i]
            if bye in (a, b):
                continue
            pairs.append((a, b))
        rounds.append(pairs)
        rotation = [rotation[0], rotation[-1], *rotation[1:-1]]
    return rounds


def build_schedule(
    club_keys: list[str],
    games_per_club_target: int,
    start_date: date,
    rest_days_weekday: list[int],
    games_per_series: int = 1,
    days_between_series: int = 0,
    groups: dict[str, str] | None = None,
    intra_cycles: int = 2,
    inter_cycles: int = 1,
    cycles_between: Callable[[str, str], int] | None = None,
    target_is_derived: bool = False,
) -> ScheduleReport:
    """Calendario de la temporada regular.

    `groups` asigna a cada club su grupo. Con uno solo —o sin `groups`— el
    calendario es el round-robin de siempre y las vueltas no se usan.

    `cycles_between(grupo_a, grupo_b)` permite que **cada división tenga sus
    propias vueltas**: una de seis clubes puede jugar cuatro vueltas internas
    mientras su hermana de cuatro juega seis, y el enfrentamiento entre ambas
    las que diga la función. Sin ella se usan `intra_cycles` e `inter_cycles`
    para todas, que es el caso simétrico.

    `target_is_derived` evita avisos redundantes cuando la cifra técnica de
    temporada se calculó a partir de la estructura declarada por fases.
    """
    if cycles_between is None:

        def cycles_between(a: str, b: str) -> int:
            return intra_cycles if a == b else inter_cycles

    con_grupos = bool(groups) and len({*groups.values()}) > 1
    if con_grupos:
        faltan = [key for key in club_keys if key not in groups]
        if faltan:
            raise ScheduleError(
                f"estos clubes no tienen grupo asignado: {', '.join(sorted(faltan)[:4])}",
                ["revisa el reparto de grupos de la edición"],
            )
    uniforme = con_grupos and _es_uniforme(groups or {}, club_keys, cycles_between)
    if con_grupos and not uniforme:
        return _build_grouped_schedule(
            club_keys=club_keys,
            groups=groups,
            games_per_club_target=games_per_club_target,
            start_date=start_date,
            rest_days_weekday=rest_days_weekday,
            games_per_series=games_per_series,
            days_between_series=days_between_series,
            cycles_between=cycles_between,
            target_is_derived=target_is_derived,
        )
    if len(club_keys) < 2:
        raise ScheduleError(
            "una competición necesita al menos 2 clubes para tener calendario",
            ["revisa `generation.club_count`"],
        )
    if len(set(club_keys)) != len(club_keys):
        raise ScheduleError("hay claves de club repetidas en la competición")

    n = len(club_keys)
    base_rounds = _circle_pairings(club_keys)
    # Con n par cada club juega n-1 partidos por ciclo; con n impar también,
    # porque en cada jornada uno descansa.
    per_cycle_games_per_club = games_per_series * (n - 1)

    warnings: list[str] = []
    cycles = max(1, round(games_per_club_target / max(1, per_cycle_games_per_club)))
    achieved = cycles * per_cycle_games_per_club
    if achieved != games_per_club_target:
        feasible = sorted(
            {per_cycle_games_per_club * c for c in range(1, 13)}
            | {per_cycle_games_per_club * cycles}
        )
        nearby = [f for f in feasible if abs(f - games_per_club_target) <= per_cycle_games_per_club]
        warnings.append(
            f"El objetivo de {games_per_club_target} partidos por club no se puede "
            f"repartir en jornadas completas con {n} clubes y series de "
            f"{games_per_series}: cada ciclo da {per_cycle_games_per_club} partidos "
            f"por club. Se programaron {achieved}. Objetivos exactos cercanos: "
            f"{', '.join(str(f) for f in nearby) or 'ninguno en el rango'}."
        )

    rest = set(rest_days_weekday)
    if len(rest) >= 7:
        raise ScheduleError(
            "no se puede descansar los siete días de la semana",
            ["deja al menos un día hábil en `rest_days_weekday`"],
        )

    games: list[ScheduledGame] = []
    current = start_date
    round_index = 0
    series_index = 0

    def next_playing_day(day: date) -> date:
        while day.weekday() in rest:
            day += timedelta(days=1)
        return day

    for cycle in range(cycles):
        for pairs in base_rounds:
            if not pairs:
                continue
            # Alternar localías por ciclo: con un número par de ciclos, cada
            # emparejamiento acaba con el mismo número de partidos en casa.
            flip = cycle % 2 == 1
            for game_in_series in range(games_per_series):
                current = next_playing_day(current)
                for home, away in pairs:
                    if flip:
                        home, away = away, home
                    games.append(
                        ScheduledGame(
                            round_index=round_index,
                            series_index=series_index,
                            game_in_series=game_in_series,
                            home_key=home,
                            away_key=away,
                            game_date=current,
                        )
                    )
                current += timedelta(days=1)
            series_index += 1
            round_index += 1
            current += timedelta(days=days_between_series)

    counts: dict[str, int] = {}
    for game in games:
        counts[game.home_key] = counts.get(game.home_key, 0) + 1
        counts[game.away_key] = counts.get(game.away_key, 0) + 1
    distinct = set(counts.values())
    if len(distinct) > 1:
        warnings.append(
            "El calendario no quedó balanceado: los clubes no juegan el mismo "
            f"número de partidos ({sorted(distinct)})."
        )

    home_counts: dict[str, int] = dict.fromkeys(club_keys, 0)
    for game in games:
        home_counts[game.home_key] += 1
    imbalance = max(home_counts.values()) - min(home_counts.values())
    if imbalance > games_per_series:
        warnings.append(
            f"Desbalance de localías de {imbalance} partidos entre el club que más "
            "juega en casa y el que menos. Un número par de ciclos lo corrige."
        )

    if con_grupos:
        # Mismas vueltas dentro y fuera del grupo: el calendario es el
        # round-robin de siempre, que reparte localías y jornadas mejor que
        # cualquier empaquetado. Los grupos siguen contando para la
        # clasificación y para el playoff, así que cada partido se etiqueta.
        games = [
            replace(
                game, matchup="intra" if groups[game.home_key] == groups[game.away_key] else "inter"
            )
            for game in games
        ]

    return ScheduleReport(
        games=games,
        games_per_club=achieved,
        requested_games_per_club=games_per_club_target,
        rounds=round_index,
        warnings=warnings,
        first_date=games[0].game_date if games else None,
        last_date=games[-1].game_date if games else None,
        games_by_club=counts,
    )


_VIRTUAL = "\x00virtual"


def _balanced_orientation(
    edges: list[tuple[str, str]], club_keys: list[str]
) -> list[tuple[str, str]]:
    """Decide quién es local en cada enfrentamiento único, repartiendo parejo.

    El problema es exactamente orientar las aristas de un grafo para que cada
    vértice tenga el mismo número de salientes que de entrantes, y eso lo
    resuelve un **recorrido euleriano**: si todos los grados son pares, el
    circuito entra y sale de cada club el mismo número de veces, así que cada
    uno es local en la mitad de sus partidos. Los clubes con un número impar de
    rivales no pueden cuadrar —les sobra o les falta un partido— y se conectan a
    un vértice virtual para que el circuito exista; su desajuste es de uno, que
    es el mínimo posible.

    Un reparto voraz («sea local el que menos veces lo ha sido») parece
    equivalente y no lo es: procesa los enfrentamientos en orden y acaba dando
    casi todos los partidos en casa a los últimos clubes de la lista.
    """
    todas = list(edges)
    adyacencia: dict[str, list[int]] = {club: [] for club in club_keys}
    for indice, (uno, otro) in enumerate(todas):
        adyacencia[uno].append(indice)
        adyacencia[otro].append(indice)

    impares = [club for club in club_keys if len(adyacencia[club]) % 2 == 1]
    if impares:
        adyacencia[_VIRTUAL] = []
        for club in impares:
            indice = len(todas)
            todas.append((_VIRTUAL, club))
            adyacencia[club].append(indice)
            adyacencia[_VIRTUAL].append(indice)

    usada = [False] * len(todas)
    cursor = dict.fromkeys(adyacencia, 0)
    orientadas: list[tuple[str, str]] = []

    for inicio in [*club_keys, *([_VIRTUAL] if impares else [])]:
        pila: list[tuple[str, tuple[str, str] | None]] = [(inicio, None)]
        while pila:
            nodo, arista = pila[-1]
            vecinos = adyacencia[nodo]
            while cursor[nodo] < len(vecinos) and usada[vecinos[cursor[nodo]]]:
                cursor[nodo] += 1
            if cursor[nodo] == len(vecinos):
                pila.pop()
                if arista is not None:
                    orientadas.append(arista)
                continue
            indice = vecinos[cursor[nodo]]
            usada[indice] = True
            uno, otro = todas[indice]
            siguiente = otro if uno == nodo else uno
            pila.append((siguiente, (nodo, siguiente)))

    return [
        (local, visita) for local, visita in orientadas if local != _VIRTUAL and visita != _VIRTUAL
    ]


def _es_uniforme(
    groups: dict[str, str],
    club_keys: list[str],
    cycles_between: Callable[[str, str], int],
) -> bool:
    """¿Todas las parejas juegan las mismas vueltas, dentro y fuera?

    Si lo son, el calendario es un round-robin normal y se construye por el
    camino de siempre, que reparte mejor jornadas y localías.
    """
    etiquetas = sorted({groups[clave] for clave in club_keys if clave in groups})
    dentro = {cycles_between(e, e) for e in etiquetas}
    fuera = {cycles_between(a, b) for a in etiquetas for b in etiquetas if a != b}
    return len(dentro) == 1 and len(fuera) == 1 and dentro == fuera


def _series_plan(
    club_keys: list[str],
    groups: dict[str, str],
    cycles_between: Callable[[str, str], int],
) -> list[tuple[str, str, str]]:
    """Series que hay que jugar: (local, visitante, tipo), en orden estable.

    Cada pareja aparece tantas veces como vueltas le correspondan: las de su
    grupo, `intra_cycles`; las de otro grupo, `inter_cycles`.

    Las vueltas pares se reparten exactas —la mitad en cada campo—, y el
    partido que sobra cuando las vueltas son impares se orienta con
    `_balanced_orientation`, que es lo que evita que los primeros clubes de la
    lista acaben jugando casi todo en casa.
    """
    plan: list[tuple[str, str, str]] = []
    sobrantes: dict[str, list[tuple[str, str]]] = {"intra": [], "inter": []}

    for i, uno in enumerate(club_keys):
        for otro in club_keys[i + 1 :]:
            misma = groups[uno] == groups[otro]
            vueltas = cycles_between(groups[uno], groups[otro])
            if not vueltas:
                continue
            tipo = "intra" if misma else "inter"
            for _ in range(vueltas // 2):
                plan.append((uno, otro, tipo))
                plan.append((otro, uno, tipo))
            if vueltas % 2:
                sobrantes[tipo].append((uno, otro))

    for tipo in ("intra", "inter"):
        for local, visita in _balanced_orientation(sobrantes[tipo], club_keys):
            plan.append((local, visita, tipo))
    return plan


def _pack_rounds(plan: list[tuple[str, str, str]]) -> list[list[tuple[str, str, str]]]:
    """Reparte las series en jornadas donde ningún club juega dos veces.

    Empaquetado voraz por «a quién le quedan más partidos»: así las jornadas del
    final no se quedan con dos clubes mirándose, que es lo que pasa si se van
    cogiendo las series en el orden en que aparecen.
    """
    restantes = list(plan)
    pendientes: dict[str, int] = {}
    for local, visita, _ in restantes:
        pendientes[local] = pendientes.get(local, 0) + 1
        pendientes[visita] = pendientes.get(visita, 0) + 1

    jornadas: list[list[tuple[str, str, str]]] = []
    while restantes:
        restantes.sort(key=lambda s: (-(pendientes[s[0]] + pendientes[s[1]]), s[0], s[1], s[2]))
        ocupados: set[str] = set()
        jornada: list[tuple[str, str, str]] = []
        sobran: list[tuple[str, str, str]] = []
        for serie in restantes:
            local, visita, _ = serie
            if local in ocupados or visita in ocupados:
                sobran.append(serie)
                continue
            jornada.append(serie)
            ocupados.add(local)
            ocupados.add(visita)
            pendientes[local] -= 1
            pendientes[visita] -= 1
        jornadas.append(sorted(jornada))
        restantes = sobran
    return jornadas


def _build_grouped_schedule(
    *,
    club_keys: list[str],
    groups: dict[str, str],
    games_per_club_target: int,
    start_date: date,
    rest_days_weekday: list[int],
    games_per_series: int,
    days_between_series: int,
    cycles_between: Callable[[str, str], int],
    target_is_derived: bool = False,
) -> ScheduleReport:
    if len(club_keys) < 2:
        raise ScheduleError(
            "una competición necesita al menos 2 clubes para tener calendario",
            ["revisa `generation.club_count`"],
        )
    if len(set(club_keys)) != len(club_keys):
        raise ScheduleError("hay claves de club repetidas en la competición")

    por_grupo: dict[str, list[str]] = {}
    for key in club_keys:
        por_grupo.setdefault(groups[key], []).append(key)
    solitarios = [
        etiqueta
        for etiqueta, miembros in por_grupo.items()
        if len(miembros) < 2 and cycles_between(etiqueta, etiqueta)
    ]
    if solitarios:
        raise ScheduleError(
            f"el grupo «{solitarios[0]}» tiene un solo club: no puede jugar vueltas "
            "dentro de su grupo",
            ["reparte los clubes o reduce el número de grupos"],
        )

    rest = set(rest_days_weekday)
    if len(rest) >= 7:
        raise ScheduleError(
            "no se puede descansar los siete días de la semana",
            ["deja al menos un día hábil en `rest_days_weekday`"],
        )

    plan = _series_plan(club_keys, groups, cycles_between)
    if not plan:
        raise ScheduleError(
            "las vueltas declaradas no producen ningún partido",
            ["revisa `structure.intra_cycles` y `structure.inter_cycles`"],
        )
    jornadas = _pack_rounds(plan)

    games: list[ScheduledGame] = []
    current = start_date
    round_index = 0
    series_index = 0

    def next_playing_day(day: date) -> date:
        while day.weekday() in rest:
            day += timedelta(days=1)
        return day

    for jornada in jornadas:
        for game_in_series in range(games_per_series):
            current = next_playing_day(current)
            for local, visita, tipo in jornada:
                games.append(
                    ScheduledGame(
                        round_index=round_index,
                        series_index=series_index,
                        game_in_series=game_in_series,
                        home_key=local,
                        away_key=visita,
                        game_date=current,
                        matchup=tipo,
                    )
                )
            current += timedelta(days=1)
        series_index += len(jornada)
        round_index += 1
        current += timedelta(days=days_between_series)

    counts: dict[str, int] = dict.fromkeys(club_keys, 0)
    for game in games:
        counts[game.home_key] += 1
        counts[game.away_key] += 1

    warnings: list[str] = []
    distintos = sorted(set(counts.values()))
    logrado = min(distintos)
    if len(distintos) > 1:
        warnings.append(
            "Los clubes no juegan todos el mismo número de partidos "
            f"({', '.join(str(d) for d in distintos)}): con grupos de tamaños "
            "distintos es inevitable, porque cada uno tiene más o menos rivales "
            "en su división. La clasificación usa porcentaje de victorias, que no "
            "depende de los partidos jugados."
        )
    if not target_is_derived and logrado != games_per_club_target:
        warnings.append(
            f"El objetivo de {games_per_club_target} partidos por club no lo fija el "
            f"calendario cuando hay divisiones: salen {logrado} de las vueltas que cada "
            f"una declara, con series de {games_per_series}. Ajusta las vueltas si "
            "quieres otra cifra; el motor no cambia las reglas por su cuenta."
        )

    home_counts: dict[str, int] = dict.fromkeys(club_keys, 0)
    for game in games:
        home_counts[game.home_key] += 1
    imbalance = max(home_counts.values()) - min(home_counts.values())
    if imbalance > games_per_series:
        warnings.append(
            f"Desbalance de localías de {imbalance} partidos entre el club que más "
            "juega en casa y el que menos. Un número par de vueltas lo corrige."
        )

    return ScheduleReport(
        games=games,
        games_per_club=logrado,
        requested_games_per_club=games_per_club_target,
        rounds=round_index,
        warnings=warnings,
        first_date=games[0].game_date if games else None,
        last_date=games[-1].game_date if games else None,
        games_by_club=counts,
    )
