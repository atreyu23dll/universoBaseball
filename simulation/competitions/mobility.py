"""Movilidad de clubes entre competiciones: ascenso y descenso.

Tres ideas que este módulo sostiene:

1. **La cuota es una sola.** Con varias ligas alimentadoras, el número total de
   plazas vive en la relación de la competición superior y se reparte entre las
   ramas. Nunca se multiplica por rama: cuatro ligas con cuota total 3 mueven
   tres clubes, no doce.
2. **Balance.** Suben tantos como bajan, salvo que el usuario configure
   explícitamente una expansión. Si un requisito de ascenso bloquea una plaza,
   se pierde también el descenso correspondiente, y se dice en una nota.
3. **Nada se inventa.** Si la clasificación no tiene suficientes clubes para
   cubrir las plazas, se levanta un error explícito en vez de mover a medias.

El módulo es puro: recibe clasificaciones ya resueltas y devuelve un plan. No
sabe nada de la base de datos, y por eso se puede probar sin servidor.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from simulation.core.errors import RuleValidationError

MOBILITY_SCHEMA_VERSION = "1.0.0"


class Direction(StrEnum):
    PROMOTED = "promoted"
    RELEGATED = "relegated"


class SelectionMethod(StrEnum):
    """Cómo se eligen los clubes que se mueven en cada extremo."""

    #: Los mejores de la tabla de la temporada regular.
    TOP_STANDINGS = "top_standings"
    #: Los peores de la tabla de la temporada regular.
    BOTTOM_STANDINGS = "bottom_standings"
    #: El campeón de la postemporada primero; el resto, por tabla.
    PLAYOFF_CHAMPION = "playoff_champion"


#: Métodos admisibles en cada extremo de la relación.
PROMOTION_METHODS = {SelectionMethod.TOP_STANDINGS, SelectionMethod.PLAYOFF_CHAMPION}
RELEGATION_METHODS = {SelectionMethod.BOTTOM_STANDINGS}


class FailurePolicy(StrEnum):
    """Qué hacer cuando un club que debería ascender no cumple los requisitos."""

    #: Asciende el siguiente clasificado que sí cumpla.
    SUBSTITUTE = "substitute"
    #: La plaza se queda vacía: nadie sube y, por balance, nadie baja por ella.
    BLOCK = "block"
    #: Asciende de todas formas y queda registrada la excepción.
    EXCEPTION = "exception"


class SelectionRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: SelectionMethod
    #: Si no se indica, se usa la cuota de la relación.
    count: int | None = Field(default=None, ge=1, le=12)


class PromotionRequirements(BaseModel):
    """Requisitos de ascenso. Todo opcional: por omisión no se exige nada."""

    model_config = ConfigDict(extra="forbid")

    min_venue_capacity: int | None = Field(default=None, ge=0, le=200_000)
    #: Deuda sobre presupuesto anual. 1.5 = deber año y medio de presupuesto.
    max_debt_to_budget: float | None = Field(default=None, ge=0.0, le=20.0)

    @property
    def any(self) -> bool:
        return self.min_venue_capacity is not None or self.max_debt_to_budget is not None


class MobilityConfig(BaseModel):
    """Configuración efectiva de una relación de ascenso/descenso.

    Vive en una sola fila —la de la relación— para que las dos competiciones
    muestren la misma regla. Es un schema tipado y versionado, no JSON opaco.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = MOBILITY_SCHEMA_VERSION
    exchange_slots: int = Field(ge=1, le=12)
    lower_selection: SelectionRule = Field(
        default_factory=lambda: SelectionRule(method=SelectionMethod.TOP_STANDINGS)
    )
    upper_selection: SelectionRule = Field(
        default_factory=lambda: SelectionRule(method=SelectionMethod.BOTTOM_STANDINGS)
    )
    eligibility_policy: Literal["ignore", "verify_before_exchange"] = "verify_before_exchange"
    requirements: PromotionRequirements = Field(default_factory=PromotionRequirements)
    on_requirement_failure: FailurePolicy = FailurePolicy.SUBSTITUTE
    #: Parte de la cuota total que le corresponde a ESTA rama. Vacío = se
    #: reparte equitativamente entre las ramas que no declaran la suya. La cuota
    #: total vive en `exchange_slots` y es la misma para todas las ramas: así no
    #: hay dos números que puedan contradecirse.
    branch_slots: int | None = Field(default=None, ge=0, le=12)
    #: El usuario puede querer una expansión deliberada: suben más de los que
    #: bajan. Por omisión está apagado y el motor exige balance.
    allow_unbalanced: bool = False
    apply_at: Literal["season_transition"] = "season_transition"
    moves_clubs: bool = True
    #: Cuánto se acerca el presupuesto del club a la escala de su nueva
    #: competición el primer año. Heurística: no hay salto instantáneo.
    budget_adaptation: float = Field(default=0.5, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _coherent(self) -> MobilityConfig:
        if self.lower_selection.method not in PROMOTION_METHODS:
            raise ValueError(
                f"«{self.lower_selection.method}» no es un criterio de ascenso; "
                f"usa uno de: {', '.join(sorted(PROMOTION_METHODS))}"
            )
        if self.upper_selection.method not in RELEGATION_METHODS:
            raise ValueError(
                f"«{self.upper_selection.method}» no es un criterio de descenso; "
                f"usa uno de: {', '.join(sorted(RELEGATION_METHODS))}"
            )
        for name, rule in (("lower", self.lower_selection), ("upper", self.upper_selection)):
            if rule.count is not None and rule.count != self.exchange_slots:
                raise ValueError(
                    f"`{name}_selection.count` dice {rule.count} y `exchange_slots` "
                    f"dice {self.exchange_slots}. La cuota es un solo número: deja "
                    "`count` vacío o pon el mismo valor."
                )
        if self.branch_slots is not None and self.branch_slots > self.exchange_slots:
            raise ValueError(
                f"esta rama pide {self.branch_slots} plazas y la cuota total de la "
                f"competición superior es {self.exchange_slots}: una rama no puede "
                "aportar más que el total"
            )
        return self


#: Campos de `MobilityConfig` cuya autoridad es la competición superior: valen
#: igual para todas sus ligas alimentadoras. Los demás (`lower_selection`,
#: `requirements`, `branch_slots`, `on_requirement_failure`, `eligibility_policy`)
#: son de cada rama, porque cada liga puede elegir a sus ascendidos con su propio
#: criterio y exigirles sus propios requisitos.
SHARED_FIELD_LABELS = {
    "exchange_slots": "la cuota total de plazas",
    "upper_selection": "el criterio de descenso",
    "allow_unbalanced": "el permiso de intercambio desbalanceado",
    "budget_adaptation": "la adaptación de presupuesto",
    "apply_at": "el momento de aplicación",
}


def parse_mobility_config(payload: Mapping[str, Any]) -> MobilityConfig:
    return MobilityConfig.model_validate(dict(payload))


class DevelopmentLinkConfig(BaseModel):
    """Vínculo filial, juvenil o de desarrollo.

    Mueve **jugadores**, nunca clubes: `moves_clubs` es literalmente `False` y
    el schema no admite otra cosa, para que una filial no pueda acabar
    tratándose como una división por un campo mal puesto.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = MOBILITY_SCHEMA_VERSION
    moves_clubs: Literal[False] = False
    allows_player_loans: bool = True
    #: Edad máxima del jugador cedido, si el vínculo la impone.
    max_player_age: int | None = Field(default=None, ge=14, le=45)
    notes: str = ""


def parse_development_config(payload: Mapping[str, Any]) -> DevelopmentLinkConfig:
    return DevelopmentLinkConfig.model_validate(dict(payload))


@dataclass(frozen=True)
class ClubRank:
    """Un club y su posición final, con lo que hace falta para decidir.

    `place_chain` es la cadena territorial del club, de lo más concreto a lo más
    general (`MX-CJS-NOR`, `MX-CJS`, `MX-CHH`, `MX`). Sirve para repartir
    descensos entre ligas regionales sin mandar a un club de Sonora a la liga de
    Chihuahua si hay alternativa.
    """

    club_id: str
    name: str
    rank: int
    is_champion: bool = False
    venue_capacity: int = 0
    debt_to_budget: float = 0.0
    place_chain: tuple[str, ...] = ()


@dataclass(frozen=True)
class BranchState:
    """Una competición con su clasificación final y su territorio."""

    competition_id: str
    name: str
    clubs: tuple[ClubRank, ...]
    territory: tuple[str, ...] = ()
    professionalization: float = 0.5
    #: Plazas que esta rama aporta, si su relación las declara explícitamente.
    declared_slots: int | None = None

    def ordered(self, method: SelectionMethod) -> list[ClubRank]:
        by_rank = sorted(self.clubs, key=lambda c: (c.rank, c.club_id))
        if method is SelectionMethod.TOP_STANDINGS:
            return by_rank
        if method is SelectionMethod.BOTTOM_STANDINGS:
            return list(reversed(by_rank))
        # PLAYOFF_CHAMPION: el campeón primero, el resto por tabla.
        champion = [c for c in by_rank if c.is_champion]
        return champion + [c for c in by_rank if not c.is_champion]


@dataclass(frozen=True)
class Movement:
    club_id: str
    club_name: str
    direction: Direction
    from_competition_id: str
    to_competition_id: str
    rank: int
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "club_id": self.club_id,
            "club_name": self.club_name,
            "direction": str(self.direction),
            "from_competition_id": self.from_competition_id,
            "to_competition_id": self.to_competition_id,
            "rank": self.rank,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RejectedClub:
    club_id: str
    club_name: str
    competition_id: str
    rank: int
    unmet: tuple[str, ...]
    policy: FailurePolicy

    def as_dict(self) -> dict[str, Any]:
        return {
            "club_id": self.club_id,
            "club_name": self.club_name,
            "competition_id": self.competition_id,
            "rank": self.rank,
            "unmet": list(self.unmet),
            "policy": str(self.policy),
        }


@dataclass
class ExchangePlan:
    total_slots: int
    branch_quotas: dict[str, int]
    movements: list[Movement] = field(default_factory=list)
    rejected: list[RejectedClub] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def promotions(self) -> list[Movement]:
        return [mv for mv in self.movements if mv.direction is Direction.PROMOTED]

    @property
    def relegations(self) -> list[Movement]:
        return [mv for mv in self.movements if mv.direction is Direction.RELEGATED]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": MOBILITY_SCHEMA_VERSION,
            "total_slots": self.total_slots,
            "branch_quotas": dict(self.branch_quotas),
            "movements": [mv.as_dict() for mv in self.movements],
            "rejected": [r.as_dict() for r in self.rejected],
            "notes": list(self.notes),
        }


def distribute_quota(
    total: int,
    branch_ids: Sequence[str],
    explicit: Mapping[str, int] | None = None,
) -> dict[str, int]:
    """Reparte la cuota **total** entre las ligas alimentadoras.

    Sin reparto explícito: equitativo, y el resto a las primeras ramas en orden
    estable por identificador, para que el reparto sea reproducible.
    """
    if not branch_ids:
        return {}
    ordered = sorted(branch_ids)
    declared = {key: int(value) for key, value in (explicit or {}).items() if value is not None}
    unknown = [key for key in declared if key not in set(ordered)]
    if unknown:
        raise RuleValidationError(
            f"el reparto de plazas menciona competiciones que no alimentan a esta: {unknown}"
        )

    undeclared = [key for key in ordered if key not in declared]
    assigned = sum(declared.values())
    if not undeclared:
        if assigned != total:
            raise RuleValidationError(
                f"el reparto por rama suma {assigned} plazas y la cuota total es {total}",
                ["corrige las plazas de alguna rama para que sumen exactamente el total"],
            )
        return {key: declared[key] for key in ordered}

    remaining = total - assigned
    if remaining < 0:
        raise RuleValidationError(
            f"las ramas con reparto explícito ya suman {assigned} plazas y la cuota "
            f"total es {total}",
            ["baja las plazas declaradas o sube la cuota total de la relación"],
        )
    base, remainder = divmod(remaining, len(undeclared))
    quotas = dict(declared)
    for index, key in enumerate(undeclared):
        quotas[key] = base + (1 if index < remainder else 0)
    return {key: quotas[key] for key in ordered}


def unmet_requirements(club: ClubRank, requirements: PromotionRequirements) -> tuple[str, ...]:
    """Requisitos de ascenso que el club no cumple, en texto legible."""
    unmet: list[str] = []
    if (
        requirements.min_venue_capacity is not None
        and club.venue_capacity < requirements.min_venue_capacity
    ):
        unmet.append(
            f"aforo de {club.venue_capacity} por debajo del mínimo exigido "
            f"({requirements.min_venue_capacity})"
        )
    if (
        requirements.max_debt_to_budget is not None
        and club.debt_to_budget > requirements.max_debt_to_budget
    ):
        unmet.append(
            f"deuda de {club.debt_to_budget:.2f} veces su presupuesto, por encima "
            f"del máximo ({requirements.max_debt_to_budget:.2f})"
        )
    return tuple(unmet)


def _select_promoted(
    branch: BranchState,
    quota: int,
    config: MobilityConfig,
) -> tuple[list[ClubRank], list[RejectedClub], list[str]]:
    """Elige los clubes que ascienden de una rama, aplicando requisitos."""
    if quota <= 0:
        return [], [], []
    candidates = branch.ordered(config.lower_selection.method)
    if len(candidates) < quota:
        raise RuleValidationError(
            f"«{branch.name}» tiene {len(candidates)} clubes clasificados y la "
            f"relación pide ascender {quota}",
            [
                "reduce las plazas de intercambio",
                "o revisa por qué la edición terminó con menos participantes",
            ],
        )

    chosen: list[ClubRank] = []
    rejected: list[RejectedClub] = []
    notes: list[str] = []
    verify = config.eligibility_policy == "verify_before_exchange" and config.requirements.any

    # `lost` son plazas que la política BLOCK deja vacías: no las hereda nadie,
    # pero tampoco se llevan por delante al resto de la cuota.
    lost = 0
    for club in candidates:
        if len(chosen) + lost >= quota:
            break
        unmet = unmet_requirements(club, config.requirements) if verify else ()
        if not unmet:
            chosen.append(club)
            continue
        rejected.append(
            RejectedClub(
                club_id=club.club_id,
                club_name=club.name,
                competition_id=branch.competition_id,
                rank=club.rank,
                unmet=unmet,
                policy=config.on_requirement_failure,
            )
        )
        if config.on_requirement_failure is FailurePolicy.EXCEPTION:
            chosen.append(club)
            notes.append(
                f"{club.name} asciende por excepción pese a no cumplir: {'; '.join(unmet)}."
            )
        elif config.on_requirement_failure is FailurePolicy.SUBSTITUTE:
            notes.append(
                f"{club.name} ({branch.name}, puesto {club.rank}) no cumple los "
                f"requisitos de ascenso: {'; '.join(unmet)}. Asciende el siguiente "
                "clasificado que sí los cumple."
            )
        else:  # BLOCK
            lost += 1
            notes.append(
                f"{club.name} ({branch.name}, puesto {club.rank}) no cumple los "
                f"requisitos de ascenso: {'; '.join(unmet)}. La plaza queda vacía: "
                "nadie la hereda y, por balance, tampoco desciende nadie por ella."
            )

    if len(chosen) < quota and config.on_requirement_failure is FailurePolicy.SUBSTITUTE:
        notes.append(
            f"«{branch.name}» solo pudo cubrir {len(chosen)} de {quota} plazas de "
            "ascenso: ningún otro club cumple los requisitos."
        )
    return chosen, rejected, notes


def _territory_rank(club: ClubRank, branch: BranchState) -> int:
    """Cuánto encaja un club en el territorio de una rama. Menor es mejor."""
    territory = set(branch.territory)
    for depth, key in enumerate(club.place_chain):
        if key in territory:
            return depth
    return len(club.place_chain) + 1


def _assign_relegations(
    relegated: Sequence[ClubRank],
    upper: BranchState,
    feeders: Sequence[BranchState],
    capacity: Mapping[str, int],
) -> tuple[list[Movement], list[str]]:
    """Reparte los descensos entre ramas respetando su cuota real.

    Cada rama recibe exactamente tantos clubes como ascendió, para que ninguna
    competición cambie de tamaño. El territorio decide la preferencia: un club
    de Sonora baja a la liga de Sonora si hay plaza allí.
    """
    remaining = {
        branch.competition_id: capacity.get(branch.competition_id, 0) for branch in feeders
    }
    by_id = {branch.competition_id: branch for branch in feeders}
    movements: list[Movement] = []
    notes: list[str] = []

    for club in relegated:
        options = [cid for cid, left in remaining.items() if left > 0]
        if not options:
            break
        options.sort(key=lambda cid: (_territory_rank(club, by_id[cid]), -remaining[cid], cid))
        target = options[0]
        if _territory_rank(club, by_id[target]) > len(club.place_chain) and len(feeders) > 1:
            notes.append(
                f"{club.name} desciende a «{by_id[target].name}» aunque su territorio "
                "no coincide: era la rama con plaza disponible."
            )
        remaining[target] -= 1
        movements.append(
            Movement(
                club_id=club.club_id,
                club_name=club.name,
                direction=Direction.RELEGATED,
                from_competition_id=upper.competition_id,
                to_competition_id=target,
                rank=club.rank,
                reason=f"puesto {club.rank} de {len(upper.clubs)} en «{upper.name}»",
            )
        )
    return movements, notes


def plan_exchange(
    upper: BranchState,
    feeders: Sequence[BranchState],
    config: MobilityConfig,
) -> ExchangePlan:
    """Resuelve quién sube y quién baja. No escribe nada: devuelve el plan."""
    if not config.moves_clubs:
        raise RuleValidationError(
            "esta relación no mueve clubes: una filial o una liga juvenil no es "
            "un eslabón de ascenso y descenso"
        )
    if not feeders:
        raise RuleValidationError("no hay ninguna competición inferior vinculada")

    quotas = distribute_quota(
        config.exchange_slots,
        [branch.competition_id for branch in feeders],
        {branch.competition_id: branch.declared_slots for branch in feeders},
    )
    plan = ExchangePlan(total_slots=config.exchange_slots, branch_quotas=quotas)

    if len(feeders) > 1:
        reparto = ", ".join(
            f"{branch.name}: {quotas[branch.competition_id]}"
            for branch in sorted(feeders, key=lambda b: b.competition_id)
        )
        plan.notes.append(
            f"La cuota total de {config.exchange_slots} plazas se reparte entre "
            f"{len(feeders)} ligas alimentadoras ({reparto}). El total no se "
            "multiplica por rama."
        )

    promoted_by_branch: dict[str, list[ClubRank]] = {}
    for branch in sorted(feeders, key=lambda b: b.competition_id):
        chosen, rejected, notes = _select_promoted(branch, quotas[branch.competition_id], config)
        promoted_by_branch[branch.competition_id] = chosen
        plan.rejected.extend(rejected)
        plan.notes.extend(notes)
        for club in chosen:
            plan.movements.append(
                Movement(
                    club_id=club.club_id,
                    club_name=club.name,
                    direction=Direction.PROMOTED,
                    from_competition_id=branch.competition_id,
                    to_competition_id=upper.competition_id,
                    rank=club.rank,
                    reason=(
                        f"campeón de «{branch.name}»"
                        if club.is_champion
                        and config.lower_selection.method is SelectionMethod.PLAYOFF_CHAMPION
                        else f"puesto {club.rank} de {len(branch.clubs)} en «{branch.name}»"
                    ),
                )
            )

    promoted_total = sum(len(clubs) for clubs in promoted_by_branch.values())
    relegation_target = config.exchange_slots if config.allow_unbalanced else promoted_total
    if relegation_target != config.exchange_slots and not config.allow_unbalanced:
        plan.notes.append(
            f"Descienden {relegation_target} clubes en vez de {config.exchange_slots}: "
            "las plazas de ascenso que quedaron sin cubrir no provocan descensos."
        )

    candidates = upper.ordered(config.upper_selection.method)
    if len(candidates) < relegation_target:
        raise RuleValidationError(
            f"«{upper.name}» tiene {len(candidates)} clubes y la relación pide "
            f"descender {relegation_target}",
            ["reduce las plazas de intercambio"],
        )
    relegated = candidates[:relegation_target]

    capacity = {cid: len(clubs) for cid, clubs in promoted_by_branch.items()}
    if config.allow_unbalanced and relegation_target != promoted_total:
        # Expansión o reducción deliberada: el reparto sigue las cuotas pedidas.
        capacity = dict(quotas)
        plan.notes.append(
            "Intercambio deliberadamente desbalanceado: las competiciones cambian de tamaño."
        )
    down_movements, down_notes = _assign_relegations(relegated, upper, feeders, capacity)
    plan.movements.extend(down_movements)
    plan.notes.extend(down_notes)

    if len(down_movements) < relegation_target:
        plan.notes.append(
            f"Solo se pudieron colocar {len(down_movements)} de {relegation_target} "
            "descensos: no hay plazas suficientes en las ligas inferiores."
        )
    return plan


# --------------------------------------------------------------------------- #
# Consecuencias económicas y de prestigio del movimiento
# --------------------------------------------------------------------------- #


def level_to_months(level: float) -> float:
    """Meses de coste de referencia que corresponden a un nivel efectivo.

    Es la inversa exacta de `resolve_effective_level`, con la misma constante de
    escala, así que deshacer el nivel devuelve la escala de recursos típica de
    esa competición. Se usa solo para comparar dos categorías entre sí.
    """
    from simulation.generation.context import LEVEL_SCALE

    return max(0.0, 10.0 ** (LEVEL_SCALE * max(0.0, min(1.0, level))) - 1.0)


def adapt_budget(
    current: Decimal,
    origin_level: float,
    destination_level: float,
    adaptation: float = 0.5,
    max_step: float = 2.0,
) -> Decimal:
    """Acerca el presupuesto del club a la escala de su nueva competición.

    El club que asciende no hereda el presupuesto medio de su nueva liga: se
    acerca una fracción (`adaptation`) y como mucho `max_step` veces por
    temporada, porque sus ingresos reales —socios, patrocinio, taquilla— tardan
    en moverse. Es una transición, no un recálculo: el modelo completo de
    ingresos y gastos vive en `simulation.economy`.
    """
    origin = level_to_months(origin_level)
    destination = level_to_months(destination_level)
    if origin <= 0:
        return current
    ratio = max(1.0 / max_step, min(max_step, destination / origin))
    factor = 1.0 + adaptation * (ratio - 1.0)
    return (current * Decimal(str(round(factor, 6)))).quantize(Decimal("1"))


def adapt_reputation(
    reputation: Mapping[str, float], direction: Direction, step: float = 0.04
) -> dict[str, float]:
    """Mueve la reputación despacio. Subir de categoría no da prestigio de golpe."""
    sign = 1.0 if direction is Direction.PROMOTED else -1.0
    out = dict(reputation)
    for scope, weight in (("local", 0.5), ("national", 1.0), ("international", 0.25)):
        if scope in out:
            out[scope] = round(max(0.0, min(1.0, float(out[scope]) + sign * step * weight)), 4)
    return out
