"""Estructura de una competición: fases, divisiones y puertas de clasificación.

El modelo anterior tenía una sola forma: `count` divisiones iguales, las mismas
vueltas para todas, los mismos clasificados por cada una, y después un cuadro.
Servía para una liga por divisiones y no para nada más.

Aquí la competición es una **secuencia de fases**, y cada fase es una de dos
cosas:

- `table`: una o varias divisiones jugando round-robin **a la vez**, cada una
  con sus propias vueltas. Una división es un subproceso de la liga, y no tiene
  por qué parecerse a sus hermanas: puede tener otro número de clubes, otras
  vueltas internas y otros clasificados.
- `bracket`: cruces eliminatorios entre los que llegaron, con sus series al
  mejor de N.

Lo que une una fase con la siguiente son las **puertas** (`Gate`): «el primero
y el segundo de cada división pasan directos» y «los dos mejores de la tabla
general entre los que no pasaron entran por repechaje» son dos puertas, con su
ruta. Esa ruta es lo que la interfaz pinta con un color y lo que decide la
siembra del cuadro.

Nada de esto cambia la regla del ADR 0004: las plazas no se declaran dos veces.
Las de una fase son la suma de los puestos de las puertas de la anterior, y el
reglamento rechaza cualquier cifra que no cuadre con esa suma.

Compatibilidad: un reglamento que no declare `stages` sigue siendo válido y se
traduce a fases con `derive_stages()`, así que los universos y los reglamentos
guardados antes de este modelo se siguen jugando igual.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StageFormat(StrEnum):
    """Qué se juega en una fase."""

    #: Round-robin en una o varias divisiones simultáneas.
    TABLE = "table"
    #: Eliminatorias con cruces y series al mejor de N.
    BRACKET = "bracket"


class GateRoute(StrEnum):
    """Por dónde entra un clasificado. La interfaz le da un color a cada ruta."""

    #: Pasa por su propio puesto en su división.
    DIRECT = "direct"
    #: Pasa por repechaje, comparándose con los de otras divisiones.
    WILDCARD = "wildcard"
    #: Entrada neutra colocada por el editor visual. Su significado lo dan la
    #: procedencia y la ronda de destino, no una etiqueta deportiva impuesta.
    SEED = "seed"


class Division(BaseModel):
    """Un subproceso de la liga: su grupo de clubes y sus propias vueltas."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=60)
    #: Clubes que la ocupan. Solo en la primera fase: en las siguientes los
    #: participantes vienen de las puertas de la fase anterior.
    slots: int = Field(default=0, ge=0, le=64)
    #: Vueltas contra cada rival de la propia división.
    intra_cycles: int = Field(default=2, ge=0, le=12)
    #: Vueltas contra cada club de las otras divisiones de su misma fase.
    inter_cycles: int = Field(default=0, ge=0, le=12)


class Gate(BaseModel):
    """Quiénes salen de una fase y por qué puerta."""

    model_config = ConfigDict(extra="forbid")

    #: División de la que salen. `None` = de la tabla general de la fase.
    division: str | None = None
    #: Puestos que pasan, contando desde 1. En una puerta de división son sus
    #: puestos; en una puerta de la tabla general son los puestos **entre los
    #: que todavía no han pasado por ninguna puerta anterior**, que es lo que
    #: significa un repechaje: «los dos mejores de los que se quedaron fuera».
    positions: list[int] = Field(min_length=1)
    route: GateRoute = GateRoute.DIRECT
    #: Lo que el usuario llamó a esta puerta. Si está vacío, se describe sola.
    label: str = Field(default="", max_length=80)
    #: Ronda del cuadro en la que aparece esta entrada. ``None`` conserva el
    #: sembrado automático de los reglamentos antiguos; 0 es la primera ronda,
    #: 1 la siguiente, etc. Esto permite dibujar un repechaje real: quienes lo
    #: juegan entran en 0 y los pases directos esperan una ronda posterior.
    target_round: int | None = Field(default=None, ge=0, le=7)
    #: Orden dentro del cajón de destino. Permite emparejar por el orden que el
    #: usuario dibujó sin convertir los futuros clubes en datos del reglamento.
    order: int | None = Field(default=None, ge=0, le=127)

    @field_validator("positions")
    @classmethod
    def _puestos_validos(cls, v: list[int]) -> list[int]:
        if any(p < 1 for p in v):
            raise ValueError("los puestos de una puerta se cuentan desde 1")
        if len(set(v)) != len(v):
            raise ValueError(f"la puerta repite puestos: {v}")
        return sorted(v)

    @property
    def size(self) -> int:
        return len(self.positions)

    def describe(self, division_label: str | None = None) -> str:
        if self.label:
            return self.label
        donde = f" de {division_label}" if division_label else " de la tabla general"
        puestos = ", ".join(str(p) for p in self.positions)
        if self.route is GateRoute.WILDCARD:
            return f"repechaje: puesto(s) {puestos}{donde}"
        if self.route is GateRoute.SEED and self.division is None:
            # Una entrada neutra de la tabla general no es el puesto N de la
            # tabla: es el puesto N entre los que no pasaron por su división.
            return f"puesto(s) {puestos} entre los que no pasaron por su división"
        return f"puesto(s) {puestos}{donde}"


class Stage(BaseModel):
    """Una fase de la competición."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=60)
    format: StageFormat = StageFormat.TABLE
    #: Solo para `table`. Una división sola es una tabla única.
    divisions: list[Division] = Field(default_factory=list)
    #: Solo para `bracket`: al mejor de N en cada ronda.
    series_lengths: list[int] = Field(default_factory=list)
    #: Quién pasa de esta fase a la siguiente. La última fase no necesita
    #: puertas: su ganador es el campeón.
    gates: list[Gate] = Field(default_factory=list)

    @field_validator("series_lengths")
    @classmethod
    def _series_impares(cls, v: list[int]) -> list[int]:
        for longitud in v:
            if longitud < 1 or longitud % 2 == 0:
                raise ValueError(
                    f"una serie al mejor de N necesita N impar y >= 1; recibido {longitud}"
                )
        return v

    @model_validator(mode="after")
    def _coherente(self) -> Stage:
        if self.format is StageFormat.TABLE:
            if not self.divisions:
                raise ValueError(f"la fase «{self.label}» es de tabla y no tiene divisiones")
            claves = [d.key for d in self.divisions]
            if len(set(claves)) != len(claves):
                raise ValueError(f"la fase «{self.label}» repite claves de división")
            etiquetas = [d.label.strip().casefold() for d in self.divisions]
            if len(set(etiquetas)) != len(etiquetas):
                raise ValueError(f"la fase «{self.label}» tiene dos divisiones con el mismo nombre")
            if len(self.divisions) == 1 and self.divisions[0].inter_cycles:
                raise ValueError(
                    f"la fase «{self.label}» tiene una sola división: no hay contra quién "
                    "jugar vueltas de fuera"
                )
            if all(d.intra_cycles == 0 for d in self.divisions) and all(
                d.inter_cycles == 0 for d in self.divisions
            ):
                raise ValueError(f"la fase «{self.label}» no juega ninguna vuelta")
        else:
            if self.divisions:
                raise ValueError(
                    f"la fase «{self.label}» es de cruces: sus participantes vienen de las "
                    "puertas de la fase anterior, no de divisiones"
                )

        for gate in self.gates:
            if gate.division is None:
                continue
            if gate.division not in {d.key for d in self.divisions}:
                raise ValueError(
                    f"la puerta de la fase «{self.label}» apunta a la división "
                    f"«{gate.division}», que no existe en ella"
                )
        # Dos puertas de la misma división no pueden sacar al mismo puesto.
        por_division: dict[str | None, set[int]] = {}
        for gate in self.gates:
            vistos = por_division.setdefault(gate.division, set())
            choque = vistos & set(gate.positions)
            if choque:
                raise ValueError(
                    f"dos puertas de la fase «{self.label}» sacan al mismo puesto {sorted(choque)}"
                )
            vistos |= set(gate.positions)
        return self

    @property
    def slots(self) -> int:
        """Clubes que ocupan la fase, si los declara."""
        return sum(d.slots for d in self.divisions)

    @property
    def qualifiers(self) -> int:
        """Cuántos salen de esta fase por sus puertas."""
        salen = 0
        for gate in self.gates:
            if gate.division is None:
                salen += gate.size
            else:
                salen += gate.size
        return salen

    @property
    def division_keys(self) -> list[str]:
        return [d.key for d in self.divisions]

    def division(self, key: str) -> Division | None:
        return next((d for d in self.divisions if d.key == key), None)

    def cycles_between(self, a: str, b: str) -> int:
        """Vueltas entre dos divisiones de esta fase.

        Dentro de una división, las suyas. Entre dos distintas, **las que pida
        la que más pida**: no puede haber dos cifras para el mismo
        enfrentamiento, y rebajar a la que pide más sería decidir por ella.
        """
        if a == b:
            division = self.division(a)
            return division.intra_cycles if division else 0
        uno, otro = self.division(a), self.division(b)
        return max(uno.inter_cycles if uno else 0, otro.inter_cycles if otro else 0)

    @property
    def is_symmetric(self) -> bool:
        """¿Todas sus divisiones juegan lo mismo y tienen el mismo tamaño?"""
        if len(self.divisions) <= 1:
            return True
        primera = self.divisions[0]
        return all(
            d.slots == primera.slots
            and d.intra_cycles == primera.intra_cycles
            and d.inter_cycles == primera.inter_cycles
            for d in self.divisions[1:]
        )


def bracket_shape(participants: int) -> tuple[int, int, int]:
    """Tamaño del cuadro, pases directos y rondas para N participantes."""
    if participants < 2:
        return 0, 0, 0
    tamaño = 1 << (participants - 1).bit_length()
    return tamaño, tamaño - participants, tamaño.bit_length() - 1


def validate_sequence(stages: list[Stage], club_count: int) -> list[str]:
    """Comprueba que las fases encajan entre sí. Devuelve los problemas.

    Devuelve una lista en vez de lanzar porque la interfaz necesita enseñar
    **todos** los desajustes mientras el usuario arrastra, no el primero.
    """
    problemas: list[str] = []
    if not stages:
        return ["la competición no tiene ninguna fase"]

    claves = [s.key for s in stages]
    if len(set(claves)) != len(claves):
        problemas.append("dos fases tienen la misma clave")

    if stages[0].format is not StageFormat.TABLE:
        problemas.append("la primera fase tiene que ser de tabla: alguien tiene que jugar")
    elif stages[0].slots != club_count:
        problemas.append(
            f"las divisiones de «{stages[0].label}» tienen {stages[0].slots} plazas y la "
            f"competición {club_count} clubes"
        )

    for indice, stage in enumerate(stages):
        if stage.format is StageFormat.TABLE:
            for division in stage.divisions:
                if indice == 0 and division.slots < 2:
                    problemas.append(
                        f"«{division.label}» se queda con {division.slots} club(es): una "
                        "división necesita al menos dos"
                    )
                if indice == 0 and division.intra_cycles == 0 and len(stage.divisions) == 1:
                    problemas.append(f"«{division.label}» no juega ninguna vuelta")
        ultima = indice == len(stages) - 1
        if not ultima and not stage.gates:
            problemas.append(
                f"de «{stage.label}» no pasa nadie a «{stages[indice + 1].label}»: falta una puerta"
            )
        if ultima and stage.gates:
            problemas.append(
                f"«{stage.label}» es la última fase y tiene puertas: no hay fase siguiente "
                "a la que mandar clasificados"
            )

        if indice == 0:
            continue
        llegan = stages[indice - 1].qualifiers
        if stage.format is StageFormat.BRACKET:
            entradas = stages[indice - 1].gates
            dibujado = any(g.target_round is not None for g in entradas)
            if llegan < 2:
                problemas.append(
                    f"a «{stage.label}» llegan {llegan} club(es): un cuadro necesita dos"
                )
            elif dibujado:
                # Cuadro dibujado: las rondas son las que puso el usuario y lo
                # que hay que comprobar es que su camino cierre. Exigirle la
                # potencia de dos prohibiría una escalerilla legítima.
                if any(g.target_round is None for g in entradas):
                    problemas.append(
                        f"«{stage.label}» mezcla entradas colocadas a mano y entradas con "
                        "siembra automática: coloca todas en una ronda"
                    )
                elif not stage.series_lengths:
                    problemas.append(f"«{stage.label}» no tiene ninguna ronda: añade al menos una")
                else:
                    problemas.extend(
                        _validate_round_entries(stage, entradas, len(stage.series_lengths))
                    )
            else:
                _, _, rondas = bracket_shape(llegan)
                if len(stage.series_lengths) != rondas:
                    problemas.append(
                        f"«{stage.label}» recibe {llegan} clasificados, que piden {rondas} "
                        f"ronda(s); se declararon {len(stage.series_lengths)} longitudes de serie"
                    )
        elif stage.slots and stage.slots != llegan:
            problemas.append(
                f"a «{stage.label}» llegan {llegan} clasificados y sus divisiones tienen "
                f"{stage.slots} plazas"
            )

    # Los puestos de una puerta tienen que existir en su división.
    for indice, stage in enumerate(stages):
        for gate in stage.gates:
            if gate.division is None:
                tope = stage.slots if indice == 0 else stages[indice - 1].qualifiers
                donde = "la tabla general"
            else:
                division = stage.division(gate.division)
                tope = division.slots if division else 0
                donde = f"«{division.label}»" if division else gate.division
            if tope and max(gate.positions) > tope:
                problemas.append(
                    f"una puerta de «{stage.label}» saca al puesto {max(gate.positions)} de "
                    f"{donde}, que solo tiene {tope}"
                )
    return problemas


def _validate_round_entries(stage: Stage, gates: list[Gate], rounds: int) -> list[str]:
    """Valida un cuadro al que pueden incorporarse clubes en rondas distintas."""
    problemas: list[str] = []
    por_ronda = [0 for _ in range(rounds)]
    for gate in gates:
        destino = gate.target_round
        if destino is None:
            continue
        if destino >= rounds:
            problemas.append(
                f"una entrada de «{stage.label}» apunta a la ronda {destino + 1}, "
                f"pero el cuadro solo tiene {rounds}"
            )
            continue
        por_ronda[destino] += gate.size

    ganadores = 0
    for indice, nuevas in enumerate(por_ronda):
        participantes = nuevas if indice == 0 else ganadores + nuevas
        if participantes < 2:
            problemas.append(
                f"la ronda {indice + 1} de «{stage.label}» recibe {participantes} "
                "club(es): necesita al menos dos"
            )
            ganadores = participantes
            continue
        if participantes % 2:
            problemas.append(
                f"la ronda {indice + 1} de «{stage.label}» recibe {participantes} "
                "clubes: falta una entrada para formar todos los cruces"
            )
        ganadores = participantes // 2
    if ganadores != 1:
        problemas.append(
            f"el camino de «{stage.label}» termina con {ganadores} posibles ganadores; "
            "debe terminar con uno"
        )
    return problemas


def derive_stages(
    *,
    club_count: int,
    labels: list[str],
    group_sizes: list[int] | None,
    intra_cycles: int,
    inter_cycles: int,
    qualifiers_per_group: int,
    wildcards: int,
    playoffs: object,
) -> list[Stage]:
    """Traduce la forma simple de `StructureRules` a fases.

    Existe para que un reglamento guardado antes de este modelo —y los que se
    sigan escribiendo con la forma corta— se jueguen por el mismo camino que
    los declarados por fases. No inventa nada: cada campo de la forma simple
    tiene su sitio exacto aquí.
    """
    cuantas = max(1, len(labels))
    if group_sizes and sum(group_sizes) == club_count:
        plazas = list(group_sizes)
    else:
        base, resto = divmod(club_count, cuantas)
        plazas = [base + 1 if i < resto else base for i in range(cuantas)]

    divisiones = [
        Division(
            key=f"d{indice + 1}",
            label=etiqueta,
            slots=plazas[indice],
            intra_cycles=intra_cycles if cuantas > 1 else max(1, intra_cycles),
            inter_cycles=inter_cycles if cuantas > 1 else 0,
        )
        for indice, etiqueta in enumerate(labels[:cuantas])
    ]

    gates: list[Gate] = []
    formato = getattr(playoffs, "format", None)
    plazas_playoff = int(getattr(playoffs, "slots", 0) or 0)
    if formato is not None and str(formato) != "none" and plazas_playoff >= 2:
        if cuantas > 1 and qualifiers_per_group:
            puestos = list(range(1, qualifiers_per_group + 1))
            gates.extend(
                Gate(division=division.key, positions=puestos, route=GateRoute.DIRECT)
                for division in divisiones
            )
            if wildcards:
                gates.append(
                    Gate(
                        division=None,
                        positions=list(range(1, wildcards + 1)),
                        route=GateRoute.WILDCARD,
                    )
                )
        else:
            gates.append(
                Gate(
                    division=None,
                    positions=list(range(1, plazas_playoff + 1)),
                    route=GateRoute.DIRECT,
                )
            )

    # Las claves son las que la base ya usa para `editions.stage` y
    # `games.stage`: así una edición en curso y una estructura derivada hablan
    # el mismo idioma sin traducciones.
    regular = Stage(
        key="regular_season",
        label="Temporada regular",
        format=StageFormat.TABLE,
        divisions=divisiones,
        gates=gates,
    )
    if not gates:
        return [regular]
    return [
        regular,
        Stage(
            key="playoffs",
            label="Postemporada",
            format=StageFormat.BRACKET,
            series_lengths=list(getattr(playoffs, "round_lengths", []) or []),
        ),
    ]
