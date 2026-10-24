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
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RULESET_SCHEMA_VERSION = "2.0.0"


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
        if self.slots & (self.slots - 1) != 0:
            raise ValueError(
                "esta versión soporta brackets de potencia de 2 (2, 4, 8, 16); "
                f"recibido {self.slots}. Byes y rondas desiguales son Etapa 2."
            )
        expected_rounds = self.slots.bit_length() - 1
        if (
            self.format is PlayoffFormat.BEST_OF_SERIES
            and len(self.round_lengths) != expected_rounds
        ):
            raise ValueError(
                f"{self.slots} plazas requieren {expected_rounds} rondas; "
                f"se declararon {len(self.round_lengths)} longitudes de serie"
            )
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
    club_count: int = Field(ge=2, le=64)
    #: De dónde pueden salir los participantes. Es una regla de admisión, no un
    #: selector de calidad: el talento vive en un mercado compartido.
    talent_pool: TalentPoolMode = TalentPoolMode.SHARED_GEOGRAPHIC
    foreign_player_limit: int | None = Field(default=None, ge=0, le=40)
    seed: int | None = Field(default=None, ge=0)


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
    relationship_mode: RelationshipMode = RelationshipMode.INDEPENDENT
    scope: Scope
    markets: list[MarketSlot] = Field(default_factory=list)
    eligibility: EligibilityRules = Field(default_factory=EligibilityRules)
    admission: AdmissionRules = Field(default_factory=AdmissionRules)
    financial_regulations: FinancialRegulations = Field(default_factory=FinancialRegulations)
    season: SeasonRules
    standings: StandingsRules = Field(default_factory=StandingsRules)
    playoffs: PlayoffRules = Field(default_factory=PlayoffRules)
    generation: GenerationRules
    prize_pool: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _cross_checks(self) -> RuleSet:
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
        if self.markets:
            declared = sum(m.slots for m in self.markets)
            if declared > self.generation.club_count:
                raise ValueError(
                    f"los cupos de mercado suman {declared} pero la competición "
                    f"tiene {self.generation.club_count} plazas"
                )
        if (
            self.scope.level is ScopeLevel.MULTINATIONAL
            and len({k.split("-")[0] for k in self.scope.place_keys}) < 2
        ):
            raise ValueError("un alcance multinacional necesita lugares de al menos dos países")
        return self

    @property
    def modality(self) -> ModalityProfile:
        """Perfil reglamentario de la modalidad elegida."""
        return modality_profile(self.participation_modality)

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
