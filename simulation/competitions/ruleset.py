"""RuleSet: las reglas que el usuario define, validadas y versionadas.

Son schemas tipados, no JSON opaco. Un `RuleSet` se congela en una
`CompetitionRuleVersion` con su checksum, y una edición apunta a esa versión:
cambiar las reglas no reescribe una temporada ya jugada.

**Frontera innegociable** (FIX V2 de Fase 1, §1 y §10.1): aquí vive la voluntad
del usuario sobre la *competición*. No hay ni puede haber un campo que decida el
presupuesto, el propietario, la plantilla administrativa, la propiedad del
estadio ni la riqueza de los clubes: eso lo genera cada institución por su
cuenta (`simulation.economy`). La única pregunta de naturaleza institucional es
`participation_modality`, y lo que define son **reglas de participación**, no
dinero.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from simulation.competitions.structure import (
    Stage,
    StageFormat,
    derive_stages,
    validate_sequence,
)

RULESET_SCHEMA_VERSION = "2.0.0"


#: Tope de equipos de una competición. Vive aquí porque no es un detalle del
#: formulario: el calendario, la tabla y el cuadro se construyen sobre él, y el
#: descubridor de universidades lo consulta para avisar cuando un territorio
#: tiene más instituciones de las que caben en una liga.
MAX_CLUBS_PER_COMPETITION = 64


class CompetitionKind(StrEnum):
    DOMESTIC_LEAGUE = "domestic_league"
    MUNICIPAL_LEAGUE = "municipal_league"
    REGIONAL_LEAGUE = "regional_league"
    NATIONAL_LEAGUE = "national_league"
    INTERNATIONAL_CLUB_LEAGUE = "international_club_league"
    DOMESTIC_CUP = "domestic_cup"
    CONTINENTAL_CLUB_CUP = "continental_club_cup"
    NATIONAL_TEAMS_TOURNAMENT = "national_teams_tournament"
    NATIONAL_TEAMS_QUALIFIER = "national_teams_qualifier"
    YOUTH_LEAGUE = "youth_league"
    RESERVE_LEAGUE = "reserve_league"
    #: Liga de centros educativos. El subtipo vive en `education.track` para
    #: que «escolar» y «formativa» sean equivalentes para el motor, pero
    #: sigan siendo visibles en el universo.
    EDUCATIONAL_LEAGUE = "educational_league"

    @property
    def is_cup(self) -> bool:
        return self in {CompetitionKind.DOMESTIC_CUP, CompetitionKind.CONTINENTAL_CLUB_CUP}

    @property
    def is_national_teams(self) -> bool:
        return self in {
            CompetitionKind.NATIONAL_TEAMS_TOURNAMENT,
            CompetitionKind.NATIONAL_TEAMS_QUALIFIER,
        }


class ParticipationModality(StrEnum):
    """Marco de participación de la competición. **No** es un nivel de riqueza.

    Lo que una modalidad determina son prácticas y acreditaciones compatibles:
    si se admite remuneración, si hace falta licencia, qué salvaguardas aplican.
    Lo que **no** determina es el patrimonio de los clubes, su propietario, su
    estadio ni su personal. En una liga llanera pueden convivir un equipo
    vecinal en campo prestado y una asociación con patrocinio sólido.
    """

    LLANERA = "llanera"
    AMATEUR_ORGANIZED = "amateur_organized"
    SCHOOL_FORMATIVE = "school_formative"
    SEMI_PROFESSIONAL = "semi_professional"
    PROFESSIONAL = "professional"


class EducationTrack(StrEnum):
    """La identidad declarada de una liga educativa.

    Ambas vías comparten las reglas de participación de la modalidad
    ``school_formative``. La distinción no es un multiplicador económico ni
    una categoría deportiva: conserva cómo se nombra y se entiende la liga en
    el universo. La vía escolar adulta usa el catálogo de universidades reales
    que se haya importado para el territorio.
    """

    SCHOOL = "school"
    FORMATIVE = "formative"


class CompensationRule(StrEnum):
    """Qué permite la competición en materia de pago a los participantes."""

    #: Sin restricción reglamentaria.
    UNRESTRICTED = "unrestricted"
    #: Solo gastos justificados: viáticos, transporte, equipamiento.
    EXPENSES_ONLY = "expenses_only"
    #: Prohibición expresa de salarios.
    NO_SALARIED_PLAYERS = "no_salaried_players"
    #: Tope salarial por club, declarado en `salary_cap`.
    SALARY_CAP = "salary_cap"


class AgeCutoff(StrEnum):
    SEASON_START = "season_start"
    CALENDAR_YEAR = "calendar_year"
    FIXED_DATE = "fixed_date"


@dataclass(frozen=True)
class ModalityProfile:
    """Perfil reglamentario que propone una modalidad.

    Son **valores por omisión de reglas**, ajustables por el usuario en
    `financial_regulations` y `admission_rules`. Ninguno es un multiplicador
    económico: no existe aquí nada que multiplique el presupuesto de un club.
    """

    modality: ParticipationModality
    default_compensation: CompensationRule
    licence_expected: bool
    #: Partidos por semana que el marco considera sostenible, como referencia
    #: de calendario. No afecta al dinero.
    sustainable_games_per_week: float
    description: str


_MODALITY_PROFILES = {
    ParticipationModality.LLANERA: ModalityProfile(
        modality=ParticipationModality.LLANERA,
        default_compensation=CompensationRule.EXPENSES_ONLY,
        licence_expected=False,
        sustainable_games_per_week=1.5,
        description=(
            "Llanera o recreativa informal. Admite equipos de barrio, grupos "
            "comunitarios, asociaciones y clubes mejor financiados, siempre que "
            "cumplan la admisión. No presupone pobreza ni ausencia de patrocinio."
        ),
    ),
    ParticipationModality.AMATEUR_ORGANIZED: ModalityProfile(
        modality=ParticipationModality.AMATEUR_ORGANIZED,
        default_compensation=CompensationRule.NO_SALARIED_PLAYERS,
        licence_expected=False,
        sustainable_games_per_week=2.0,
        description=(
            "Amateur organizada. Prioriza registros y prácticas de amateurismo. "
            "La solvencia de un club no lo convierte en profesional."
        ),
    ),
    ParticipationModality.SCHOOL_FORMATIVE: ModalityProfile(
        modality=ParticipationModality.SCHOOL_FORMATIVE,
        default_compensation=CompensationRule.NO_SALARIED_PLAYERS,
        licence_expected=False,
        sustainable_games_per_week=1.5,
        description=(
            "Escolar o formativa. La adscripción escolar puede ser requisito de "
            "elegibilidad, y con menores se exigen salvaguardas. No obliga a que "
            "cada club sea una escuela con patrimonio propio."
        ),
    ),
    ParticipationModality.SEMI_PROFESSIONAL: ModalityProfile(
        modality=ParticipationModality.SEMI_PROFESSIONAL,
        default_compensation=CompensationRule.UNRESTRICTED,
        licence_expected=False,
        sustainable_games_per_week=3.0,
        description=(
            "Semiprofesional. Conviven dedicaciones y compensaciones distintas "
            "según contrato y contexto. No obliga a estadio propio ni a un "
            "modelo único de organización."
        ),
    ),
    ParticipationModality.PROFESSIONAL: ModalityProfile(
        modality=ParticipationModality.PROFESSIONAL,
        default_compensation=CompensationRule.UNRESTRICTED,
        licence_expected=True,
        sustainable_games_per_week=5.0,
        description=(
            "Profesional. Puede exigir licencia y contratos, pero los recursos "
            "de sus clubes varían mucho: ni riqueza ilimitada ni un mismo modelo "
            "jurídico para todos."
        ),
    ),
}


def modality_profile(modality: ParticipationModality) -> ModalityProfile:
    return _MODALITY_PROFILES[modality]


class ScopeLevel(StrEnum):
    MUNICIPAL = "municipal"
    REGIONAL = "regional"
    NATIONAL = "national"
    MULTINATIONAL = "multinational"


class RelationshipMode(StrEnum):
    INDEPENDENT = "independent"
    DEPENDENT = "dependent"


class TalentPoolMode(StrEnum):
    SHARED_GEOGRAPHIC = "shared_geographic"
    LOCAL_ONLY = "local_only"
    OPEN_INTERNATIONAL = "open_international"


class StandingsPrimary(StrEnum):
    WIN_PERCENTAGE = "win_percentage"
    WINS = "wins"
    POINTS = "points"


class Tiebreaker(StrEnum):
    HEAD_TO_HEAD = "head_to_head"
    RUN_DIFFERENTIAL = "run_differential"
    RUNS_FOR = "runs_for"
    FEWEST_RUNS_AGAINST = "fewest_runs_against"
    COIN_FLIP = "coin_flip"


class PlayoffFormat(StrEnum):
    NONE = "none"
    BEST_OF_SERIES = "best_of_series"
    SINGLE_ELIMINATION = "single_elimination"


class PairingPolicy(StrEnum):
    """Cómo se forma cada cruce de una ronda.

    Las dos primeras **resiembran**: miran la tabla de la temporada regular y
    rehacen los cruces con los que siguen vivos. Las dos últimas no, y esa es
    la diferencia entre una postemporada de liga y un cuadro de copa.
    """

    #: Mejor contra peor entre los supervivientes. Es la resiembra de la MLB.
    HIGH_LOW = "high_low"
    #: Vecinos de la tabla: primero contra segundo, tercero contra cuarto.
    ADJACENT = "adjacent"
    #: Las llaves no se mueven: el ganador de un cruce se enfrenta al del cruce
    #: de al lado, como en un cuadro de copa dibujado de antemano.
    FIXED = "fixed"
    #: Sorteo reproducible: el mismo reglamento da siempre los mismos cruces.
    DRAW = "draw"


class PlayoffSeeding(StrEnum):
    """Quién decide la forma del cuadro."""

    #: La deduce de las plazas: el cuadro es la potencia de dos que las cabe y
    #: las mejores siembras se saltan la primera ronda. Es lo que hacían los
    #: reglamentos anteriores a este campo, y sigue siendo el valor por omisión.
    AUTO = "auto"
    #: La dibujó el editor: `round_lengths` dice cuántas rondas hay y cada
    #: puerta dice en cuál entra su plaza. El motor no infiere pases directos.
    STAGED = "staged"


class GroupAssignment(StrEnum):
    """Cómo se reparten los clubes entre los grupos de una competición."""

    #: Por cercanía: los vecinos caen en el mismo grupo. Es lo que hacen las
    #: divisiones de verdad, y abarata los viajes.
    GEOGRAPHIC = "geographic"
    #: Repartiendo los clubes fuertes para igualar los grupos. Es una decisión
    #: de competitividad, no de geografía.
    BALANCED = "balanced"
    #: El usuario nombra los grupos y dice cuántas plazas tiene cada uno.
    DECLARED = "declared"


class StandingsScope(StrEnum):
    """Qué tabla manda cuando hay grupos."""

    #: Solo la tabla de cada grupo.
    GROUP = "group"
    #: Solo la tabla general.
    OVERALL = "overall"
    #: Las dos: la del grupo para clasificar, la general para los repechajes.
    BOTH = "both"


class TerritoryMode(StrEnum):
    """Cómo se delimita el territorio de una competición (FIX V2 §4.3)."""

    #: Una o varias unidades administrativas resueltas.
    ADMINISTRATIVE_AREA = "administrative_area"
    #: Radio en kilómetros desde una entidad resuelta.
    RADIUS = "radius"
    #: Conjunto explícito de territorios, posiblemente de varios países.
    TERRITORY_SET = "territory_set"


class Scope(BaseModel):
    """Territorio de la competición.

    Dos formas de declararlo, y una es mejor que la otra:

    - `entity_ids`: identificadores de **entidades geográficas resueltas** del
      gazetteer mundial. Es la vía buena: el territorio queda fijado a una
      identidad con fuente, no a un texto.
    - `place_keys`: claves de lugares ya presentes en el universo. Es la vía del
      fixture curado, anterior al gazetteer, y se conserva para no romper los
      universos existentes.

    Un nombre escrito a mano no es ninguna de las dos cosas: la creación lo
    rechaza con `GEOGRAPHY_UNRESOLVED` en vez de generar un mundo que presuma
    ser contextual (FIX V2 §13, caso T07).
    """

    model_config = ConfigDict(extra="forbid")

    level: ScopeLevel
    country_code: str | None = None
    place_keys: list[str] = Field(default_factory=list)
    #: Entidades resueltas del gazetteer mundial.
    entity_ids: list[str] = Field(default_factory=list)
    mode: TerritoryMode = TerritoryMode.ADMINISTRATIVE_AREA
    #: Solo para `mode = radius`: kilómetros desde la primera entidad.
    radius_km: float | None = Field(default=None, gt=0, le=1500)

    @field_validator("place_keys", "entity_ids")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("el territorio no admite lugares repetidos")
        return v

    @model_validator(mode="after")
    def _has_territory(self) -> Scope:
        if not self.place_keys and not self.entity_ids:
            raise ValueError(
                "el territorio necesita al menos un lugar: `entity_ids` con entidades "
                "resueltas del gazetteer, o `place_keys` del universo"
            )
        if self.mode is TerritoryMode.RADIUS:
            if not self.entity_ids:
                raise ValueError("una delimitación por radio parte de una entidad resuelta")
            if self.radius_km is None:
                raise ValueError("una delimitación por radio necesita `radius_km`")
        return self


class PointsSystem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    win: int = 1
    loss: int = 0
    tie: int = 0


class StandingsRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: StandingsPrimary = StandingsPrimary.WIN_PERCENTAGE
    tiebreakers: list[Tiebreaker] = Field(
        default_factory=lambda: [Tiebreaker.HEAD_TO_HEAD, Tiebreaker.RUN_DIFFERENTIAL]
    )
    points: PointsSystem = Field(default_factory=PointsSystem)

    @model_validator(mode="after")
    def _points_needed(self) -> StandingsRules:
        if self.primary is StandingsPrimary.POINTS and self.points.win <= self.points.loss:
            raise ValueError("con criterio de puntos, ganar debe valer más que perder")
        return self


class PlayoffRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slots: int = 0
    format: PlayoffFormat = PlayoffFormat.NONE
    round_lengths: list[int] = Field(default_factory=list)
    #: Quién fija la forma del cuadro. Con `staged`, las rondas son las de
    #: `round_lengths` y la entrada de cada plaza la dicen las puertas.
    seeding: PlayoffSeeding = PlayoffSeeding.AUTO
    #: Nombres de las rondas. Vacío conserva «Ronda 1», «Ronda 2»…
    round_labels: list[str] = Field(default_factory=list)
    #: Política de cruces por ronda. Vacío conserva mejor contra peor.
    round_pairings: list[PairingPolicy] = Field(default_factory=list)

    @field_validator("round_lengths")
    @classmethod
    def _odd_series(cls, v: list[int]) -> list[int]:
        for length in v:
            if length < 1 or length % 2 == 0:
                raise ValueError(
                    f"una serie al mejor de N necesita N impar y >= 1; recibido {length}"
                )
        return v

    @model_validator(mode="after")
    def _coherent(self) -> PlayoffRules:
        if self.format is PlayoffFormat.NONE:
            if self.slots:
                raise ValueError("hay plazas de playoff pero el formato es 'none'")
            return self
        if self.slots < 2:
            raise ValueError("un playoff necesita al menos 2 plazas")
        if self.seeding is PlayoffSeeding.STAGED:
            # Con el cuadro dibujado, las rondas no se deducen de las plazas:
            # son las que el usuario puso, y que su camino cierre con un solo
            # campeón lo comprueba `validate_sequence` con las puertas delante.
            if not self.round_lengths:
                raise ValueError("un cuadro dibujado necesita al menos una ronda")
        elif self.format is PlayoffFormat.BEST_OF_SERIES and len(self.round_lengths) != self.rounds:
            raise ValueError(
                f"{self.slots} plazas requieren {self.rounds} rondas "
                f"({self.byes} pase(s) directo(s) a la segunda); se declararon "
                f"{len(self.round_lengths)} longitudes de serie"
            )
        if self.round_labels and len(self.round_labels) != len(self.round_lengths):
            raise ValueError(
                "los nombres de las rondas tienen que corresponder uno a uno con sus series"
            )
        if any(not label.strip() for label in self.round_labels):
            raise ValueError("una ronda no puede tener el nombre vacío")
        if self.round_pairings and len(self.round_pairings) != len(self.round_lengths):
            raise ValueError("cada ronda necesita exactamente una política de emparejamiento")
        return self

    @property
    def staged(self) -> bool:
        """¿El cuadro lo dibujó el editor en vez de deducirse de las plazas?"""
        return self.seeding is PlayoffSeeding.STAGED

    def pairing_for(self, round_index: int) -> PairingPolicy:
        if round_index < len(self.round_pairings):
            return self.round_pairings[round_index]
        return PairingPolicy.HIGH_LOW

    def best_of_for(self, round_index: int) -> int:
        """Longitud de la serie de una ronda, sin salirse de la lista."""
        if round_index < len(self.round_lengths):
            return self.round_lengths[round_index]
        return self.round_lengths[-1] if self.round_lengths else 1

    def label_for(self, round_index: int) -> str:
        """Nombre de una ronda: el que le puso el usuario o su número."""
        if round_index < len(self.round_labels):
            return self.round_labels[round_index]
        return f"Ronda {round_index + 1}"

    @property
    def bracket_size(self) -> int:
        """Tamaño del cuadro: la potencia de 2 que cabe a los clasificados."""
        if self.slots < 2:
            return 0
        return 1 << (self.slots - 1).bit_length()

    @property
    def byes(self) -> int:
        """Clasificados que se saltan la primera ronda.

        Con seis plazas el cuadro es de ocho, así que dos siembras esperan en la
        segunda ronda. Es lo que pasa cuando una competición clasifica a los
        campeones de dos divisiones más un par de repechajes: seis no es potencia
        de dos y antes había que redondear el reglamento a la fuerza.
        """
        return self.bracket_size - self.slots

    @property
    def rounds(self) -> int:
        """Rondas que hacen falta para resolver el cuadro deducido."""
        return max(0, self.bracket_size.bit_length() - 1)

    @property
    def effective_rounds(self) -> int:
        """Rondas que se van a jugar: las dibujadas o las que pide el cuadro.

        Un cuadro dibujado puede tener más rondas que plazas dan de sí —una
        escalerilla donde cada ronda incorpora a uno— y por eso las cuenta su
        lista de series, no el logaritmo de las plazas.
        """
        return len(self.round_lengths) if self.staged else self.rounds

    @property
    def first_round_series(self) -> int:
        """Series de la primera ronda: los que no tienen pase directo."""
        return (self.slots - self.byes) // 2


class GroupSlot(BaseModel):
    """Un grupo declarado por el usuario, con su nombre y sus plazas."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=40)
    slots: int = Field(ge=2, le=32)


class StructureRules(BaseModel):
    """Grupos, divisiones o conferencias dentro de una misma competición.

    Una competición sin grupos es `count = 1`, que es lo que había antes y
    sigue comportándose igual: una tabla única y un calendario de vueltas
    completas.

    Con grupos, el calendario deja de ser un round-robin uniforme: cada club
    juega `intra_cycles` vueltas contra los de su grupo y `inter_cycles`
    contra los de los demás. Esa asimetría es el punto de tener divisiones
    —se juega más contra el vecino— y es también la razón por la que el
    objetivo de partidos por club pasa a ser una consecuencia del reglamento
    en vez de una cifra que se pide: el motor dice cuántos salen y advierte si
    no coincide con lo pedido, en vez de ajustar las reglas en silencio.

    La clasificación sigue siendo **una sola** por club, calculada sobre todos
    sus partidos: una tabla de grupo no es un torneo aparte, es la misma
    temporada mirada por divisiones. Lo que el grupo decide es quién clasifica.
    """

    model_config = ConfigDict(extra="forbid")

    #: Número de grupos. 1 = competición de tabla única.
    count: int = Field(default=1, ge=1, le=16)
    #: Nombres de los grupos. Si faltan, se numeran.
    groups: list[GroupSlot] = Field(default_factory=list)
    assignment: GroupAssignment = GroupAssignment.GEOGRAPHIC
    #: Vueltas completas dentro del grupo.
    intra_cycles: int = Field(default=2, ge=0, le=12)
    #: Vueltas completas contra los clubes de los otros grupos.
    inter_cycles: int = Field(default=1, ge=0, le=12)
    standings_scope: StandingsScope = StandingsScope.BOTH
    #: Clasificados directos por grupo.
    qualifiers_per_group: int = Field(default=1, ge=0, le=8)
    #: Plazas de repechaje, que salen de la tabla general entre los no
    #: clasificados. Es lo que hace falta para que un grupo fuerte no pierda a
    #: su segundo mejor club.
    wildcards: int = Field(default=0, ge=0, le=16)
    #: Fases de la competición, cuando se declaran a mano. Es el modelo
    #: completo: divisiones que no tienen por qué parecerse entre sí y puertas
    #: de clasificación con su ruta. Vacío significa «la forma simple de
    #: arriba», que se traduce a fases con `derive_stages()`.
    stages: list[Stage] = Field(default_factory=list)

    @property
    def has_groups(self) -> bool:
        if self.stages:
            return len(self.stages[0].divisions) > 1
        return self.count > 1

    @property
    def declared(self) -> bool:
        """¿La estructura se declaró por fases o con la forma simple?"""
        return bool(self.stages)

    @property
    def table_stage(self) -> Stage | None:
        """La fase de tabla con la que arranca la competición."""
        return self.stages[0] if self.stages else None

    def cycles_between_labels(
        self, club_count: int, playoffs: PlayoffRules
    ) -> Callable[[str, str], int]:
        """Vueltas entre dos divisiones, por su etiqueta.

        Es lo que `build_schedule` necesita: la inscripción de cada club guarda
        la **etiqueta** de su división, no su clave. Con la forma simple
        devuelve las mismas vueltas para todas; con fases declaradas, las de
        cada una.
        """
        stage = self.effective_stages(club_count, playoffs)[0]
        por_etiqueta = {d.label: d for d in stage.divisions}

        def vueltas(a: str, b: str) -> int:
            uno, otro = por_etiqueta.get(a), por_etiqueta.get(b)
            if a == b:
                return uno.intra_cycles if uno else 0
            return max(uno.inter_cycles if uno else 0, otro.inter_cycles if otro else 0)

        return vueltas

    def effective_stages(self, club_count: int, playoffs: PlayoffRules) -> list[Stage]:
        """Las fases declaradas, o las que implica la forma simple."""
        if self.stages:
            return list(self.stages)
        return derive_stages(
            club_count=club_count,
            labels=self.labels,
            group_sizes=[g.slots for g in self.groups] if self.groups else None,
            intra_cycles=self.intra_cycles,
            inter_cycles=self.inter_cycles,
            qualifiers_per_group=self.qualifiers_per_group,
            wildcards=self.wildcards,
            playoffs=playoffs,
        )

    @property
    def labels(self) -> list[str]:
        """Nombres de las divisiones de la primera fase."""
        if self.stages:
            return [d.label for d in self.stages[0].divisions]
        if self.groups:
            return [g.label for g in self.groups]
        if self.count == 1:
            return ["General"]
        return [f"Grupo {i + 1}" for i in range(self.count)]

    @property
    def playoff_slots(self) -> int:
        """Plazas de playoff que esta estructura produce."""
        if self.stages:
            return self.stages[0].qualifiers if len(self.stages) > 1 else 0
        return self.count * self.qualifiers_per_group + self.wildcards

    @model_validator(mode="after")
    def _coherent(self) -> StructureRules:
        if self.stages:
            # Con fases declaradas, la forma simple no se usa: dos modelos de
            # la misma estructura podrían contradecirse.
            if self.groups or self.count != 1:
                raise ValueError(
                    "la estructura se declara por fases (`stages`) o con la forma simple "
                    "(`count` y `groups`), no con las dos a la vez"
                )
            if len(self.stages) > 4:
                raise ValueError(
                    f"se declararon {len(self.stages)} fases: el motor encadena hasta cuatro, "
                    "y más que eso suele ser un error de edición"
                )
            if any(s.format is StageFormat.BRACKET for s in self.stages[:-1]):
                raise ValueError(
                    "una fase de cruces solo puede ser la última: de un cuadro sale un "
                    "campeón, no una clasificación para otra fase"
                )
            return self
        if self.groups:
            if len(self.groups) != self.count:
                raise ValueError(
                    f"se declararon {len(self.groups)} grupos y `count` dice "
                    f"{self.count}: son el mismo número o no hay estructura"
                )
            etiquetas = [g.label.strip().casefold() for g in self.groups]
            if len(set(etiquetas)) != len(etiquetas):
                raise ValueError("dos grupos no pueden llamarse igual")
        elif self.assignment is GroupAssignment.DECLARED and self.count > 1:
            raise ValueError(
                "con reparto declarado hay que nombrar los grupos y sus plazas en `groups`"
            )
        if not self.has_groups:
            return self
        if self.intra_cycles == 0 and self.inter_cycles == 0:
            raise ValueError("una competición con grupos necesita jugar alguna vuelta")
        if self.qualifiers_per_group == 0 and self.wildcards == 0:
            # No es un error: una liga por divisiones puede no tener playoff.
            return self
        return self


class SeasonRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    games_per_club_target: int = Field(ge=2, le=250)
    start_date_offset_days: int = Field(default=0, ge=0, le=365)
    #: Días entre el final de una edición y el arranque de la siguiente. Es el
    #: hueco en el que se resuelven ascensos y descensos antes de que la nueva
    #: temporada tenga calendario.
    offseason_days: int = Field(default=14, ge=1, le=180)
    #: Días de descanso ENTRE jornadas. 0 = se juega en días consecutivos,
    #: que es lo normal en béisbol; súbelo para calendarios de fin de semana.
    days_between_series: int = Field(default=0, ge=0, le=14)
    games_per_series: int = Field(default=1, ge=1, le=7)
    max_games_per_day_per_club: Literal[1, 2] = 1
    rest_days_weekday: list[int] = Field(default_factory=lambda: [0])
    allow_ties: bool = False
    extra_innings: bool = True
    designated_hitter: bool = True
    roster_size: int = Field(default=26, ge=14, le=40)
    mercy_rule_run_diff: int | None = Field(default=None, ge=5, le=30)
    mercy_rule_after_inning: int = Field(default=7, ge=4, le=9)

    @field_validator("rest_days_weekday")
    @classmethod
    def _valid_weekdays(cls, v: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("los días de descanso son 0=lunes .. 6=domingo")
        if len(set(v)) > 5:
            raise ValueError("no se puede descansar más de 5 días por semana")
        return sorted(set(v))


class EligibilityRules(BaseModel):
    """Quién puede inscribirse. Es una restricción declarativa, no una subliga.

    Crear una competición 8–12 **no** crea otra de 13–17: quien supera la edad
    sigue existiendo en el universo y podrá inscribirse donde cumpla las normas.
    """

    model_config = ConfigDict(extra="forbid")

    minimum_age: int = Field(default=18, ge=4, le=75)
    #: Sin tope si es `None`: una liga 40+ no tiene edad máxima.
    maximum_age: int | None = Field(default=None, ge=4, le=99)
    age_cutoff: AgeCutoff = AgeCutoff.SEASON_START
    #: `MM-DD`, obligatorio cuando el corte es una fecha fija del reglamento.
    cutoff_month_day: str | None = Field(default=None, pattern=r"^\d{2}-\d{2}$")
    #: Quien cumple años después del corte termina la temporada en su categoría.
    keeps_category_through_season: bool = True
    #: Salvaguarda obligatoria en competiciones con menores.
    minor_safeguarding: bool = False
    residency_required: bool = False
    #: Vacío = cualquier nacionalidad. No es un límite de extranjeros por club.
    eligible_nationalities: list[str] = Field(default_factory=list)

    @property
    def involves_minors(self) -> bool:
        return self.minimum_age < 18

    @model_validator(mode="after")
    def _coherent(self) -> EligibilityRules:
        if self.maximum_age is not None and self.maximum_age < self.minimum_age:
            raise ValueError(
                f"la edad máxima ({self.maximum_age}) no puede ser menor que la "
                f"mínima ({self.minimum_age})"
            )
        if self.age_cutoff is AgeCutoff.FIXED_DATE and not self.cutoff_month_day:
            raise ValueError("un corte de fecha fija necesita `cutoff_month_day` en formato MM-DD")
        if self.involves_minors and not self.minor_safeguarding:
            raise ValueError(
                f"una competición con edad mínima {self.minimum_age} incluye menores: "
                "`minor_safeguarding` tiene que estar activado. Elegir «infantil» no "
                "equivale por sí solo a una autorización de seguridad."
            )
        return self


class AdmissionRules(BaseModel):
    """Exigencias **regulatorias** para participar. No describen a los clubes.

    «Hace falta certificado de seguridad de la instalación» es una regla.
    «Todos los equipos serán autogestionados y pobres» no lo es.
    """

    model_config = ConfigDict(extra="forbid")

    amateur_status_required: bool = False
    facility_safety_certification_required: bool = False
    licence_required: bool = False
    minimum_venue_capacity: int | None = Field(default=None, ge=0, le=200_000)
    #: Mínimo de inscritos activos por equipo que exige el reglamento.
    minimum_active_roster: int | None = Field(default=None, ge=6, le=40)


class FinancialRegulations(BaseModel):
    """Normas económicas de la competición, no decisiones de cada club.

    Fijar `no_salaried_players` obliga al motor a respetarlo; **no** decide
    quién paga las pelotas, si hay propietario ni cuánto dinero reúne cada
    institución.
    """

    model_config = ConfigDict(extra="forbid")

    #: Vacío = se adopta el de la modalidad (`modality_profile`).
    compensation_rule: CompensationRule | None = None
    salary_cap: Decimal | None = Field(default=None, ge=0)
    #: Aportación obligatoria a la competición (inscripción, arbitraje común).
    entry_fee: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _cap_needs_amount(self) -> FinancialRegulations:
        if self.compensation_rule is CompensationRule.SALARY_CAP and self.salary_cap is None:
            raise ValueError("un tope salarial necesita el importe en `salary_cap`")
        if self.salary_cap is not None and self.compensation_rule not in (
            CompensationRule.SALARY_CAP,
            None,
        ):
            raise ValueError(
                "hay un importe de tope salarial con una regla de compensación que no es "
                "`salary_cap`"
            )
        return self


class GenerationRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Plazas objetivo. Si el territorio no las sostiene, el motor advierte en
    #: la previsualización; nunca inventa instituciones a la fuerza.
    club_count: int = Field(ge=2, le=MAX_CLUBS_PER_COMPETITION)
    #: De dónde pueden salir los participantes. Es una regla de admisión, no un
    #: selector de calidad: el talento vive en un mercado compartido.
    talent_pool: TalentPoolMode = TalentPoolMode.SHARED_GEOGRAPHIC
    foreign_player_limit: int | None = Field(default=None, ge=0, le=40)
    seed: int | None = Field(default=None, ge=0)


class UniversityParticipant(BaseModel):
    """Una universidad real, resuelta desde el catálogo antes de estructurar.

    Se congela en el reglamento que se previsualizó. Así el motor no consulta
    la red al crear una edición ni vuelve a elegir instituciones distintas por
    azar: el conjunto de equipos es exactamente el que el usuario vio.
    """

    model_config = ConfigDict(extra="forbid")

    catalog_id: str = Field(min_length=1, max_length=48)
    source: str = Field(min_length=1, max_length=32)
    source_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=2, max_length=220)
    country_code: str = Field(min_length=2, max_length=3)
    admin1_code: str | None = Field(default=None, max_length=24)
    admin2_code: str | None = Field(default=None, max_length=48)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    #: Qué clase de centro es y en qué localidad del gazetteer cae. Son datos
    #: de presentación —ayudan a reconocer la institución en la lista— y por
    #: eso admiten faltar: un reglamento guardado antes de que existieran
    #: sigue siendo válido.
    institution_type: str | None = Field(default=None, max_length=80)
    locality_name: str | None = Field(default=None, max_length=200)
    founded_year: int | None = Field(default=None, ge=800, le=2200)


class EducationRules(BaseModel):
    """Datos propios de una competición escolar o formativa.

    ``universities`` no es un selector de clubes. Para la vía escolar de 18+
    lo rellena el descubridor territorial con **todas** las universidades
    encontradas; el servidor compara ese conjunto con el catálogo antes de
    generar. Una liga de cinco universidades tiene cinco participantes, no un
    número objetivo que el generador complete con equipos ficticios.
    """

    model_config = ConfigDict(extra="forbid")

    track: EducationTrack
    universities: list[UniversityParticipant] = Field(default_factory=list)

    @field_validator("universities")
    @classmethod
    def _unique_universities(
        cls, values: list[UniversityParticipant]
    ) -> list[UniversityParticipant]:
        ids = [item.catalog_id for item in values]
        if len(set(ids)) != len(ids):
            raise ValueError("una universidad no puede participar dos veces")
        return values


class MarketSlot(BaseModel):
    """Cupo territorial explícito, para ligas multinacionales de clubes."""

    model_config = ConfigDict(extra="forbid")

    place_key: str
    slots: int = Field(default=1, ge=1, le=16)


class RuleSet(BaseModel):
    """Contrato completo de una competición."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = RULESET_SCHEMA_VERSION
    name: str = Field(min_length=2, max_length=120)
    alias: str | None = Field(default=None, max_length=32)
    kind: CompetitionKind
    #: La **única** pregunta de naturaleza institucional del formulario.
    participation_modality: ParticipationModality = ParticipationModality.AMATEUR_ORGANIZED
    #: Se declara únicamente cuando la modalidad es `school_formative`. Guarda
    #: el rastro escolar o formativo sin convertirlo en una segunda "clase" de
    #: competición: una liga municipal puede ser escolar sin dejar de ser
    #: municipal.
    education: EducationRules | None = None
    relationship_mode: RelationshipMode = RelationshipMode.INDEPENDENT
    scope: Scope
    markets: list[MarketSlot] = Field(default_factory=list)
    eligibility: EligibilityRules = Field(default_factory=EligibilityRules)
    admission: AdmissionRules = Field(default_factory=AdmissionRules)
    financial_regulations: FinancialRegulations = Field(default_factory=FinancialRegulations)
    season: SeasonRules
    structure: StructureRules = Field(default_factory=StructureRules)
    standings: StandingsRules = Field(default_factory=StandingsRules)
    playoffs: PlayoffRules = Field(default_factory=PlayoffRules)
    generation: GenerationRules
    prize_pool: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _cross_checks(self) -> RuleSet:
        if self.participation_modality is ParticipationModality.SCHOOL_FORMATIVE:
            if self.education is None:
                raise ValueError(
                    "la modalidad escolar o formativa necesita indicar si es `school` o `formative`"
                )
        elif self.education is not None:
            raise ValueError("`education` solo se declara con la modalidad `school_formative`")

        if self.requires_real_universities:
            assert self.education is not None
            found = len(self.education.universities)
            if found < 2:
                raise ValueError(
                    "una liga escolar de 18+ necesita al menos dos universidades reales "
                    "resueltas en su territorio"
                )
            if self.generation.club_count != found:
                raise ValueError(
                    f"la consulta territorial encontró {found} universidades y la liga "
                    f"declara {self.generation.club_count} equipos: en una liga escolar "
                    "adulta participan exactamente las instituciones encontradas"
                )
        if self.playoffs.slots > self.generation.club_count:
            raise ValueError(
                f"{self.playoffs.slots} plazas de playoff con solo "
                f"{self.generation.club_count} clubes: no pueden clasificar más "
                "equipos que los que compiten"
            )
        if self.kind.is_national_teams:
            raise ValueError(
                "las competiciones de selecciones son Etapa 3 y no están "
                "implementadas; el motor rechaza crearlas en vez de generar una "
                "liga de clubes disfrazada"
            )
        if self.structure.declared:
            # Con fases declaradas, la coherencia la comprueba el modelo de
            # estructura, que sabe de divisiones asimétricas y puertas.
            problemas = validate_sequence(self.structure.stages, self.generation.club_count)
            if problemas:
                raise ValueError("; ".join(problemas))
            cuadro = next(
                (s for s in self.structure.stages if s.format is StageFormat.BRACKET), None
            )
            if cuadro is None:
                if self.playoffs.format is not PlayoffFormat.NONE:
                    raise ValueError(
                        "el reglamento declara postemporada y la estructura no tiene fase "
                        "de cruces: añade la fase o quita el playoff"
                    )
            else:
                llegan = self.structure.stages[0].qualifiers
                if self.playoffs.format is PlayoffFormat.NONE:
                    raise ValueError(
                        "la estructura tiene una fase de cruces y el reglamento dice que no "
                        "hay postemporada"
                    )
                if self.playoffs.slots != llegan:
                    raise ValueError(
                        f"a la fase de cruces llegan {llegan} clasificados por sus puertas y "
                        f"`playoffs.slots` dice {self.playoffs.slots}. Las plazas las fijan "
                        "las puertas, no se declaran dos veces."
                    )
                if (
                    self.playoffs.format is PlayoffFormat.BEST_OF_SERIES
                    and cuadro.series_lengths
                    and list(self.playoffs.round_lengths) != list(cuadro.series_lengths)
                ):
                    raise ValueError(
                        "las longitudes de serie del playoff y las de la fase de cruces no "
                        "coinciden: son el mismo dato"
                    )
            return self
        if self.structure.has_groups:
            if self.generation.club_count < 2 * self.structure.count:
                raise ValueError(
                    f"{self.structure.count} grupos con {self.generation.club_count} "
                    "clubes: cada grupo necesita al menos dos para tener calendario"
                )
            if self.structure.groups:
                plazas = sum(g.slots for g in self.structure.groups)
                if plazas != self.generation.club_count:
                    raise ValueError(
                        f"las plazas de los grupos suman {plazas} y la competición "
                        f"tiene {self.generation.club_count}: declara el mismo número"
                    )
            if self.playoffs.format is not PlayoffFormat.NONE:
                # Autoridad única: con grupos, las plazas de playoff las fija la
                # estructura. Dos números que pueden contradecirse no existen.
                esperadas = self.structure.playoff_slots
                if self.playoffs.slots != esperadas:
                    raise ValueError(
                        f"con {self.structure.count} grupos, "
                        f"{self.structure.qualifiers_per_group} clasificado(s) por grupo "
                        f"y {self.structure.wildcards} repechaje(s), el playoff tiene "
                        f"{esperadas} plazas; el reglamento declara "
                        f"{self.playoffs.slots}. Cambia la estructura, no las plazas."
                    )
        if self.markets:
            declared = sum(m.slots for m in self.markets)
            if declared > self.generation.club_count:
                raise ValueError(
                    f"los cupos de mercado suman {declared} pero la competición "
                    f"tiene {self.generation.club_count} plazas"
                )
        if (
            self.scope.level is ScopeLevel.MULTINATIONAL
            and not self.scope.entity_ids
            and len({k.split("-")[0] for k in self.scope.place_keys}) < 2
        ):
            raise ValueError("un alcance multinacional necesita lugares de al menos dos países")
        return self

    @property
    def modality(self) -> ModalityProfile:
        """Perfil reglamentario de la modalidad elegida."""
        return modality_profile(self.participation_modality)

    @property
    def requires_real_universities(self) -> bool:
        """Si esta edición sustituye el generador aleatorio por universidades.

        La regla es deliberadamente estrecha: la vía *escolar* de 18 años o
        más. La vía formativa y las categorías escolares con menores conservan
        el generador de programas deportivos que ya aplica salvaguardas.
        """
        return bool(
            self.education is not None
            and self.education.track is EducationTrack.SCHOOL
            and self.eligibility.minimum_age >= 18
        )

    @property
    def effective_compensation_rule(self) -> CompensationRule:
        """Regla de pago vigente: la que fijó el usuario o la de la modalidad."""
        return self.financial_regulations.compensation_rule or self.modality.default_compensation

    @property
    def allows_player_salaries(self) -> bool:
        return self.effective_compensation_rule in (
            CompensationRule.UNRESTRICTED,
            CompensationRule.SALARY_CAP,
        )

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    def checksum(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def effective_seed(self, master_seed: int) -> int:
        """Semilla efectiva: la del RuleSet si el usuario la fijó, si no la del universo."""
        return self.generation.seed if self.generation.seed is not None else master_seed


def parse_ruleset(payload: dict[str, Any]) -> RuleSet:
    return RuleSet.model_validate(payload)
