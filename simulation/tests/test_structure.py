"""Estructura por fases: divisiones que no se parecen y puertas con ruta.

El modelo anterior solo sabía hacer divisiones iguales. Lo que se comprueba
aquí es la flexibilidad que pide el editor: una división de seis equipos con
cuatro vueltas internas junto a otra de cuatro con seis, cada una con sus
propios clasificados, y un repechaje que mira a los que se quedaron fuera.
"""

from __future__ import annotations

from datetime import date

import pytest

from simulation.competitions.playoffs import qualifiers_from_gates
from simulation.competitions.ruleset import RuleSet
from simulation.competitions.schedule import build_schedule
from simulation.competitions.structure import (
    BracketFeed,
    BracketFeedOutcome,
    BracketKey,
    BracketKeyFormat,
    Division,
    Gate,
    GateRoute,
    Stage,
    StageFormat,
    bracket_shape,
    consolation_keys,
    derive_stages,
    validate_sequence,
)

REGULAR = Stage(
    key="regular",
    label="Temporada regular",
    divisions=[
        Division(key="norte", label="Norte", slots=6, intra_cycles=4, inter_cycles=1),
        Division(key="sur", label="Sur", slots=4, intra_cycles=6, inter_cycles=1),
    ],
    gates=[
        Gate(division="norte", positions=[1, 2]),
        Gate(division="sur", positions=[1]),
        Gate(positions=[1], route=GateRoute.WILDCARD, label="Repechaje"),
    ],
)
CUADRO = Stage(
    key="cuadro", label="Postemporada", format=StageFormat.BRACKET, series_lengths=[3, 5]
)


def test_una_division_no_tiene_que_parecerse_a_sus_hermanas() -> None:
    assert not REGULAR.is_symmetric
    assert REGULAR.slots == 10
    assert REGULAR.qualifiers == 4
    # Cada una juega sus vueltas, y entre ellas la que más pida.
    assert REGULAR.cycles_between("norte", "norte") == 4
    assert REGULAR.cycles_between("sur", "sur") == 6
    assert REGULAR.cycles_between("norte", "sur") == 1
    assert REGULAR.cycles_between("sur", "norte") == 1


def test_el_calendario_respeta_las_vueltas_de_cada_division() -> None:
    clubes = [f"c{i:02d}" for i in range(10)]
    grupos = {clave: ("Norte" if i < 6 else "Sur") for i, clave in enumerate(clubes)}
    por_etiqueta = {"Norte": "norte", "Sur": "sur"}

    informe = build_schedule(
        club_keys=clubes,
        games_per_club_target=30,
        start_date=date(2042, 3, 20),
        rest_days_weekday=[0],
        groups=grupos,
        cycles_between=lambda a, b: REGULAR.cycles_between(por_etiqueta[a], por_etiqueta[b]),
    )

    rivales: dict[tuple[str, str], int] = {}
    for juego in informe.games:
        pareja = tuple(sorted((juego.home_key, juego.away_key)))
        rivales[pareja] = rivales.get(pareja, 0) + 1
    for (uno, otro), partidos in rivales.items():
        misma = grupos[uno] == grupos[otro]
        esperado = (4 if grupos[uno] == "Norte" else 6) if misma else 1
        assert partidos == esperado, f"{uno} contra {otro}: {partidos}, esperados {esperado}"

    # Norte: 5 rivales × 4 + 4 de fuera = 24. Sur: 3 × 6 + 6 = 24.
    assert set(informe.games_by_club.values()) == {24}

    por_dia: dict[date, list[str]] = {}
    for juego in informe.games:
        por_dia.setdefault(juego.game_date, []).extend([juego.home_key, juego.away_key])
    for dia, equipos in por_dia.items():
        assert len(equipos) == len(set(equipos)), f"doble partido el {dia}"

    en_casa = dict.fromkeys(clubes, 0)
    for juego in informe.games:
        en_casa[juego.home_key] += 1
    assert max(en_casa.values()) - min(en_casa.values()) <= 1


def test_divisiones_de_tamanos_distintos_juegan_numeros_distintos_de_partidos() -> None:
    """Y se dice, en vez de disimularlo."""
    fase = Stage(
        key="r",
        label="Regular",
        divisions=[
            Division(key="a", label="A", slots=6, intra_cycles=2, inter_cycles=1),
            Division(key="b", label="B", slots=4, intra_cycles=2, inter_cycles=1),
        ],
    )
    clubes = [f"c{i:02d}" for i in range(10)]
    grupos = {clave: ("A" if i < 6 else "B") for i, clave in enumerate(clubes)}
    informe = build_schedule(
        club_keys=clubes,
        games_per_club_target=14,
        start_date=date(2042, 3, 20),
        rest_days_weekday=[0],
        groups=grupos,
        cycles_between=lambda x, y: fase.cycles_between(x.lower(), y.lower()),
    )
    jugados = set(informe.games_by_club.values())
    # A: 5 × 2 + 4 = 14. B: 3 × 2 + 6 = 12.
    assert jugados == {14, 12}
    assert any("no juegan todos el mismo número" in aviso for aviso in informe.warnings)


def test_las_puertas_deciden_quien_pasa_y_por_donde() -> None:
    ranked = [
        ("n1", "Norte"),
        ("s1", "Sur"),
        ("s2", "Sur"),
        ("n2", "Norte"),
        ("n3", "Norte"),
        ("s3", "Sur"),
    ]
    clasificados = qualifiers_from_gates(ranked, REGULAR, slots=4)
    por_clave = {q.entry_key: q for q in clasificados}

    assert set(por_clave) == {"n1", "n2", "s1", "s2"}
    assert por_clave["n1"].route == "group_winner"
    assert por_clave["n1"].reason == "campeón de Norte"
    assert por_clave["n2"].reason == "segundo de Norte"
    assert por_clave["s1"].reason == "campeón de Sur"
    # s2 es el segundo de Sur, y Sur solo da una plaza directa: entra por el
    # repechaje, que mira a los que se quedaron fuera de todas las puertas.
    assert por_clave["s2"].route == "wildcard"
    assert por_clave["s2"].reason == "Repechaje"
    # Y la siembra sale de la tabla general, no del orden de las puertas.
    assert [q.entry_key for q in clasificados] == ["n1", "s1", "s2", "n2"]


def test_una_puerta_general_cuenta_sobre_los_que_no_han_pasado() -> None:
    fase = Stage(
        key="r",
        label="Regular",
        divisions=[
            Division(key="a", label="A", slots=3, intra_cycles=2, inter_cycles=1),
            Division(key="b", label="B", slots=3, intra_cycles=2, inter_cycles=1),
        ],
        gates=[
            Gate(division="a", positions=[1]),
            Gate(division="b", positions=[1]),
            Gate(positions=[1, 2], route=GateRoute.WILDCARD),
        ],
    )
    ranked = [
        ("a1", "A"),
        ("a2", "A"),
        ("b1", "B"),
        ("a3", "A"),
        ("b2", "B"),
        ("b3", "B"),
    ]
    clasificados = qualifiers_from_gates(ranked, fase, slots=4)
    # a1 y b1 por su división; después, los dos mejores de los restantes son
    # a2 y a3 —no b2—, porque el repechaje mira la tabla general.
    assert [q.entry_key for q in clasificados] == ["a1", "a2", "b1", "a3"]
    rutas = {q.entry_key: q.route for q in clasificados}
    assert rutas == {
        "a1": "group_winner",
        "b1": "group_winner",
        "a2": "wildcard",
        "a3": "wildcard",
    }


def test_la_secuencia_de_fases_se_valida_entera() -> None:
    assert validate_sequence([REGULAR, CUADRO], 10) == []

    problemas = validate_sequence([REGULAR, CUADRO], 12)
    assert any("10 plazas" in p for p in problemas)

    corto = Stage(key="c", label="Cuadro", format=StageFormat.BRACKET, series_lengths=[3])
    assert any("2 ronda(s)" in p for p in validate_sequence([REGULAR, corto], 10))

    sin_salida = Stage(
        key="r2",
        label="Regular",
        divisions=[Division(key="u", label="Única", slots=10, intra_cycles=2)],
    )
    assert any("falta una puerta" in p for p in validate_sequence([sin_salida, CUADRO], 10))


def test_un_repechaje_puede_alimentar_una_ronda_con_pases_directos() -> None:
    regular = Stage(
        key="regular",
        label="Regular",
        divisions=[Division(key="u", label="General", slots=6, intra_cycles=2)],
        gates=[
            Gate(
                division="u",
                positions=[1, 2],
                route=GateRoute.DIRECT,
                target_round=1,
            ),
            Gate(
                division="u",
                positions=[3, 4, 5, 6],
                route=GateRoute.WILDCARD,
                target_round=0,
            ),
        ],
    )
    cuadro = Stage(
        key="playoffs",
        label="Postemporada",
        format=StageFormat.BRACKET,
        series_lengths=[1, 3, 5],
    )

    assert validate_sequence([regular, cuadro], 6) == []


def test_el_editor_detecta_una_ronda_con_entrada_huerfana() -> None:
    regular = Stage(
        key="regular",
        label="Regular",
        divisions=[Division(key="u", label="General", slots=4, intra_cycles=2)],
        gates=[
            Gate(division="u", positions=[1, 2, 3], target_round=0),
            Gate(division="u", positions=[4], target_round=1),
        ],
    )
    cuadro = Stage(
        key="playoffs",
        label="Postemporada",
        format=StageFormat.BRACKET,
        series_lengths=[1, 3],
    )

    assert any("falta una entrada" in issue for issue in validate_sequence([regular, cuadro], 4))


def test_una_fase_de_tabla_no_puede_tener_una_division_de_un_club() -> None:
    fase = Stage(
        key="r",
        label="Regular",
        divisions=[
            Division(key="a", label="A", slots=9, intra_cycles=2, inter_cycles=1),
            Division(key="b", label="B", slots=1, intra_cycles=2, inter_cycles=1),
        ],
    )
    assert any("al menos dos" in p for p in validate_sequence([fase], 10))


def test_dos_puertas_no_pueden_sacar_al_mismo_puesto() -> None:
    with pytest.raises(ValueError, match="mismo puesto"):
        Stage(
            key="r",
            label="Regular",
            divisions=[Division(key="a", label="A", slots=6, intra_cycles=2)],
            gates=[Gate(division="a", positions=[1, 2]), Gate(division="a", positions=[2])],
        )


def test_el_cuadro_se_dimensiona_solo() -> None:
    assert bracket_shape(4) == (4, 0, 2)
    assert bracket_shape(6) == (8, 2, 3)
    assert bracket_shape(5) == (8, 3, 3)
    assert bracket_shape(1) == (0, 0, 0)


def test_la_forma_corta_se_traduce_a_fases_sin_inventar_nada() -> None:
    """Un reglamento guardado antes de este modelo se juega por el mismo camino."""
    payload = {
        "name": "Liga con Divisiones",
        "kind": "national_league",
        "scope": {"level": "national", "country_code": "MX", "place_keys": ["MX"]},
        "season": {"games_per_club_target": 40},
        "structure": {
            "count": 2,
            "intra_cycles": 4,
            "inter_cycles": 2,
            "qualifiers_per_group": 2,
            "wildcards": 2,
        },
        "playoffs": {"slots": 6, "format": "best_of_series", "round_lengths": [3, 5, 7]},
        "generation": {"club_count": 8, "seed": 1},
    }
    ruleset = RuleSet.model_validate(payload)
    assert not ruleset.structure.declared
    fases = ruleset.structure.effective_stages(8, ruleset.playoffs)

    # Las claves son las que la base usa para la fase de una edición, así que
    # una estructura derivada y una edición en curso hablan el mismo idioma.
    assert [s.key for s in fases] == ["regular_season", "playoffs"]
    regular = fases[0]
    assert [(d.label, d.slots, d.intra_cycles, d.inter_cycles) for d in regular.divisions] == [
        ("Grupo 1", 4, 4, 2),
        ("Grupo 2", 4, 4, 2),
    ]
    assert regular.is_symmetric
    assert regular.qualifiers == 6
    assert fases[1].series_lengths == [3, 5, 7]
    assert validate_sequence(fases, 8) == []


def test_sin_playoff_la_forma_corta_no_crea_fase_de_cruces() -> None:
    fases = derive_stages(
        club_count=12,
        labels=["General"],
        group_sizes=None,
        intra_cycles=2,
        inter_cycles=0,
        qualifiers_per_group=0,
        wildcards=0,
        playoffs=type("P", (), {"format": "none", "slots": 0, "round_lengths": []})(),
    )
    assert len(fases) == 1
    assert fases[0].gates == []


def test_el_reglamento_rechaza_declarar_las_plazas_dos_veces() -> None:
    base = {
        "name": "Liga por Fases",
        "kind": "national_league",
        "scope": {"level": "national", "country_code": "MX", "place_keys": ["MX"]},
        "season": {"games_per_club_target": 30},
        "generation": {"club_count": 10, "seed": 1},
        "structure": {"stages": [REGULAR.model_dump(mode="json"), CUADRO.model_dump(mode="json")]},
    }
    valido = RuleSet.model_validate(
        {**base, "playoffs": {"slots": 4, "format": "best_of_series", "round_lengths": [3, 5]}}
    )
    assert valido.structure.declared
    assert valido.structure.playoff_slots == 4

    with pytest.raises(ValueError, match="no se declaran dos veces"):
        RuleSet.model_validate(
            {
                **base,
                "playoffs": {
                    "slots": 6,
                    "format": "best_of_series",
                    "round_lengths": [3, 5, 7],
                },
            }
        )


def test_un_cuadro_dibujado_puede_tener_mas_rondas_que_plazas() -> None:
    """Una escalerilla: cuatro plazas en tres rondas, incorporando una por ronda.

    El cuadro deducido pediría dos rondas para cuatro plazas. Un cuadro
    dibujado no se mide así: lo que tiene que cuadrar es que cada ronda forme
    cruces completos y que el camino acabe con un solo campeón.
    """
    regular = Stage(
        key="regular",
        label="Regular",
        divisions=[Division(key="u", label="General", slots=8, intra_cycles=2)],
        gates=[
            Gate(division="u", positions=[3, 4], route=GateRoute.SEED, target_round=0),
            Gate(division="u", positions=[2], route=GateRoute.SEED, target_round=1),
            Gate(division="u", positions=[1], route=GateRoute.SEED, target_round=2),
        ],
    )
    cuadro = Stage(
        key="playoffs",
        label="Postemporada",
        format=StageFormat.BRACKET,
        series_lengths=[1, 3, 5],
    )

    assert validate_sequence([regular, cuadro], 8) == []


def test_un_cuadro_dibujado_con_una_ronda_de_mas_no_termina_en_campeon() -> None:
    """Si sobra una ronda, el camino no cierra y se dice en vez de inventar."""
    regular = Stage(
        key="regular",
        label="Regular",
        divisions=[Division(key="u", label="General", slots=4, intra_cycles=2)],
        gates=[Gate(division="u", positions=[1, 2, 3, 4], route=GateRoute.SEED, target_round=0)],
    )
    cuadro = Stage(
        key="playoffs",
        label="Postemporada",
        format=StageFormat.BRACKET,
        series_lengths=[1, 3, 5],
    )

    problemas = validate_sequence([regular, cuadro], 4)
    assert any("necesita al menos dos" in p for p in problemas)


def test_un_cuadro_dibujado_sin_rondas_se_rechaza() -> None:
    regular = Stage(
        key="regular",
        label="Regular",
        divisions=[Division(key="u", label="General", slots=4, intra_cycles=2)],
        gates=[Gate(division="u", positions=[1, 2], route=GateRoute.SEED, target_round=0)],
    )
    cuadro = Stage(key="playoffs", label="Postemporada", format=StageFormat.BRACKET)

    assert any("no tiene ninguna ronda" in p for p in validate_sequence([regular, cuadro], 4))


def test_las_plazas_de_la_tabla_general_se_numeran_sobre_la_misma_lista() -> None:
    """Repartir el repechaje en varias puertas no desplaza su numeración.

    El editor escribe una puerta por plaza para que cada una lleve su ronda de
    entrada. Si cada puerta contase sus puestos sobre lo que dejó la anterior,
    «el 2.º de los restantes» pasaría a significar «el 3.º», y el usuario
    vería entrar a un club distinto del que dibujó. Las puertas de la tabla
    general miran todas la misma lista de descartados.
    """
    fase = Stage(
        key="r",
        label="Regular",
        divisions=[
            Division(key="a", label="A", slots=3, intra_cycles=2, inter_cycles=1),
            Division(key="b", label="B", slots=3, intra_cycles=2, inter_cycles=1),
        ],
        gates=[
            Gate(division="a", positions=[1], route=GateRoute.SEED, target_round=1, order=0),
            Gate(division="b", positions=[1], route=GateRoute.SEED, target_round=1, order=1),
            # Dos plazas de la tabla general, en dos puertas y en rondas
            # distintas: siguen siendo el 1.º y el 2.º de los restantes.
            Gate(positions=[1], route=GateRoute.SEED, target_round=0, order=2),
            Gate(positions=[2], route=GateRoute.SEED, target_round=0, order=3),
        ],
    )
    ranked = [
        ("a1", "A"),
        ("a2", "A"),
        ("b1", "B"),
        ("a3", "A"),
        ("b2", "B"),
        ("b3", "B"),
    ]
    clasificados = qualifiers_from_gates(ranked, fase, slots=4)

    # El orden es el dibujado, porque el cuadro lo dibujó el editor.
    assert [q.entry_key for q in clasificados] == ["a1", "b1", "a2", "a3"]
    por_clave = {q.entry_key: q for q in clasificados}
    assert por_clave["a2"].reason == "mejor registro entre los no clasificados"
    assert por_clave["a3"].reason == "segundo entre los no clasificados"
    assert por_clave["a2"].route == "wildcard"
    assert [por_clave[c].entry_round for c in ("a1", "b1", "a2", "a3")] == [1, 1, 0, 0]


def test_grafo_de_llaves_acepta_cinco_segundos_con_una_miniliga() -> None:
    divisiones = [
        Division(key=f"d{i}", label=f"División {i}", slots=3, intra_cycles=2, inter_cycles=0)
        for i in range(1, 6)
    ]
    regular = Stage(
        key="regular",
        label="Regular",
        divisions=divisiones,
        gates=[Gate(key=f"segundo-{i}", division=f"d{i}", positions=[2]) for i in range(1, 6)],
    )
    playoff = Stage(
        key="playoff",
        label="Postemporada",
        format=StageFormat.BRACKET,
        bracket_keys=[
            BracketKey(
                key="grupo",
                label="Mini-liga de acceso",
                row=1,
                column=0,
                format=BracketKeyFormat.MINI_LEAGUE,
                feeds=[
                    BracketFeed(source=f"segundo-{i}", outcome=BracketFeedOutcome.SEED)
                    for i in range(1, 4)
                ],
                qualifying_positions=[1],
            ),
            BracketKey(
                key="serie",
                label="Serie de acceso",
                row=1,
                column=1,
                feeds=[
                    BracketFeed(source="segundo-4", outcome=BracketFeedOutcome.SEED),
                    BracketFeed(source="segundo-5", outcome=BracketFeedOutcome.SEED),
                ],
                best_of=3,
            ),
            BracketKey(
                key="final",
                label="Final",
                row=2,
                column=0,
                feeds=[
                    BracketFeed(source="grupo", outcome=BracketFeedOutcome.POSITION, position=1),
                    BracketFeed(source="serie", outcome=BracketFeedOutcome.WINNER),
                ],
                best_of=5,
            ),
        ],
    )

    assert validate_sequence([regular, playoff], club_count=15) == []


def test_grafo_de_llaves_rechaza_una_entrada_sin_destino() -> None:
    regular = Stage(
        key="regular",
        label="Regular",
        divisions=[Division(key="d", label="Única", slots=4, intra_cycles=2)],
        gates=[
            Gate(key="uno", division="d", positions=[1]),
            Gate(key="dos", division="d", positions=[2]),
            Gate(key="tres", division="d", positions=[3]),
        ],
    )
    playoff = Stage(
        key="playoff",
        label="Postemporada",
        format=StageFormat.BRACKET,
        bracket_keys=[
            BracketKey(
                key="final",
                label="Final",
                row=1,
                column=0,
                feeds=[
                    BracketFeed(source="uno", outcome=BracketFeedOutcome.SEED),
                    BracketFeed(source="dos", outcome=BracketFeedOutcome.SEED),
                ],
            )
        ],
    )

    assert "la entrada «tres» no está conectada a ninguna llave" in validate_sequence(
        [regular, playoff], club_count=4
    )


def _cuadro_de_cuatro(*extra: BracketKey) -> tuple[Stage, Stage]:
    """Semifinales y final de cuatro plazas, más las llaves que se añadan."""
    regular = Stage(
        key="regular",
        label="Regular",
        divisions=[Division(key="u", label="General", slots=8, intra_cycles=2)],
        gates=[Gate(key=f"p{i}", division="u", positions=[i]) for i in range(1, 5)],
    )
    cuadro = Stage(
        key="playoff",
        label="Postemporada",
        format=StageFormat.BRACKET,
        bracket_keys=[
            BracketKey(
                key="s1",
                label="Semifinal 1",
                row=1,
                column=0,
                feeds=[
                    BracketFeed(source="p1", outcome=BracketFeedOutcome.SEED),
                    BracketFeed(source="p4", outcome=BracketFeedOutcome.SEED),
                ],
                best_of=3,
            ),
            BracketKey(
                key="s2",
                label="Semifinal 2",
                row=1,
                column=1,
                feeds=[
                    BracketFeed(source="p2", outcome=BracketFeedOutcome.SEED),
                    BracketFeed(source="p3", outcome=BracketFeedOutcome.SEED),
                ],
                best_of=3,
            ),
            BracketKey(
                key="final",
                label="Final",
                row=2,
                column=0,
                feeds=[
                    BracketFeed(source="s1", outcome=BracketFeedOutcome.WINNER),
                    BracketFeed(source="s2", outcome=BracketFeedOutcome.WINNER),
                ],
                best_of=5,
            ),
            *extra,
        ],
    )
    return regular, cuadro


def test_el_partido_por_el_tercer_puesto_no_es_un_segundo_campeon() -> None:
    """Conectar los dos perdedores crea una llave que no disputa el título.

    Es lo que hace el editor cuando el usuario arrastra la salida «Perdedor»
    de las dos semifinales al mismo cruce. Si su ganador contase como salida
    final, el grafo tendría dos campeones y el motor lo rechazaría.
    """
    tercero = BracketKey(
        key="tercero",
        label="Tercer puesto",
        row=2,
        column=1,
        feeds=[
            BracketFeed(source="s1", outcome=BracketFeedOutcome.LOSER),
            BracketFeed(source="s2", outcome=BracketFeedOutcome.LOSER),
        ],
        best_of=1,
    )
    regular, cuadro = _cuadro_de_cuatro(tercero)

    assert validate_sequence([regular, cuadro], club_count=8) == []
    assert consolation_keys(cuadro.bracket_keys) == {"tercero"}


def test_una_llave_que_recibe_un_ganador_si_disputa_el_titulo() -> None:
    """La consolación se hereda perdiendo; un ganador la rompe."""
    repesca = BracketKey(
        key="repesca",
        label="Repesca",
        row=2,
        column=1,
        feeds=[
            BracketFeed(source="s1", outcome=BracketFeedOutcome.LOSER),
            BracketFeed(source="s2", outcome=BracketFeedOutcome.LOSER),
        ],
        best_of=1,
    )
    # El ganador de la repesca vuelve al cuadro: deja de ser consolación
    # porque su salida ya no es final, la consume la gran final.
    gran_final = BracketKey(
        key="gran",
        label="Gran final",
        row=3,
        column=0,
        feeds=[
            BracketFeed(source="final", outcome=BracketFeedOutcome.WINNER),
            BracketFeed(source="repesca", outcome=BracketFeedOutcome.WINNER),
        ],
        best_of=5,
    )
    regular, cuadro = _cuadro_de_cuatro(repesca, gran_final)

    assert validate_sequence([regular, cuadro], club_count=8) == []
    assert consolation_keys(cuadro.bracket_keys) == {"repesca"}


def test_dos_finales_de_verdad_siguen_siendo_un_error() -> None:
    """La regla se relaja para la consolación, no para el título."""
    otra_final = BracketKey(
        key="otra",
        label="Otra final",
        row=2,
        column=1,
        feeds=[
            BracketFeed(source="s1", outcome=BracketFeedOutcome.LOSER),
            BracketFeed(source="p1", outcome=BracketFeedOutcome.SEED),
        ],
        best_of=5,
    )
    regular, cuadro = _cuadro_de_cuatro(otra_final)

    problemas = validate_sequence([regular, cuadro], club_count=8)
    assert any("debe dejar un campeón" in p for p in problemas)
