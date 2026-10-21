"""Contexto de mercado: por qué una liga barrial no es una liga nacional.

Nada aquí es una tabla de valores fijos por etiqueta. Cada número sale de una
fórmula sobre el perfil regional y las reglas del usuario, y queda anotado en
`GenerationRecord` para que la interfaz pueda responder «este presupuesto viene
de tamaño de mercado y nivel de profesionalización».

Advertencia honesta: los coeficientes son **heurísticas sin calibrar** contra
datos económicos reales. Ver `docs/simulation-calibration.md`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal

from simulation.competitions.ruleset import (
    ContextualLevel,
    RuleSet,
    ScopeLevel,
)
from simulation.core.provenance import Confidence, GenerationRecord
from simulation.geography.model import Place, PlaceKind, PlaceTree

PROCEDURE_VERSION = "context/1.0.0"

# Peso de cada componente en el índice de profesionalización. Suman 1.
_W_ECONOMY = 0.45
_W_MARKET = 0.30
_W_CULTURE = 0.25

# Ajuste por alcance territorial. Es un empujón, NO un techo: la especificación
# prohíbe que el alcance por sí solo determine el grado de profesionalización.
_SCOPE_NUDGE = {
    ScopeLevel.MUNICIPAL: -0.12,
    ScopeLevel.REGIONAL: -0.04,
    ScopeLevel.NATIONAL: 0.03,
    ScopeLevel.MULTINATIONAL: 0.08,
}

_EXPLICIT_LEVEL_SCORE = {
    ContextualLevel.AMATEUR: 0.18,
    ContextualLevel.SEMI_PROFESSIONAL: 0.42,
    ContextualLevel.PROFESSIONAL: 0.68,
    ContextualLevel.ELITE: 0.9,
}

_TIER_BOUNDS = (
    (0.30, ContextualLevel.AMATEUR),
    (0.55, ContextualLevel.SEMI_PROFESSIONAL),
    (0.80, ContextualLevel.PROFESSIONAL),
    (1.01, ContextualLevel.ELITE),
)

# Unidad monetaria base del presupuesto por "unidad de mercado". Heurística.
_BUDGET_UNIT = Decimal("40000")


def market_pull(population: int) -> float:
    """Atracción de mercado en 0-1 a partir de la población captable.

    Logarítmica: duplicar habitantes no duplica el mercado deportivo.
    """
    if population <= 0:
        return 0.0
    return max(0.0, min(1.0, math.log10(population) / 7.0))


def score_to_tier(score: float) -> ContextualLevel:
    for bound, tier in _TIER_BOUNDS:
        if score < bound:
            return tier
    return ContextualLevel.ELITE


@dataclass
class MarketProfile:
    """Perfil del mercado local de un club concreto."""

    place_key: str
    place_name: str
    catchment_population: int
    economy_index: float
    culture_index: float
    infrastructure_index: float
    cost_of_living_index: float
    confidence: Confidence
    elevation_m: int
    lat: float
    lon: float

    @property
    def pull(self) -> float:
        return market_pull(self.catchment_population)

    @property
    def training_opportunity(self) -> float:
        """Oportunidad de formación, 0-1.

        Esto es lo que el entorno afecta: cuántos jóvenes encuentran campo,
        entrenador y competencia. **No** es un modificador de capacidad innata
        por origen, y el motor no tiene ninguno.
        """
        return max(
            0.05,
            min(
                1.0,
                0.45 * self.culture_index
                + 0.35 * self.infrastructure_index
                + 0.20 * self.economy_index,
            ),
        )


@dataclass
class CompetitionContext:
    """Lo que el ecosistema de la competición implica, ya resuelto y explicado."""

    ruleset_name: str
    scope_level: ScopeLevel
    professionalization_score: float
    professionalization_tier: ContextualLevel
    economy_score: float
    maturity_score: float
    aggregate_population: int
    eligible_markets: list[MarketProfile]
    currency: str = "MXN"
    record: GenerationRecord = field(default=None)  # type: ignore[assignment]

    @property
    def talent_mean(self) -> float:
        """Centro de la distribución de habilidad de la competición, 0-1.

        Una liga más profesional concentra mejores jugadores porque puede
        pagarlos y atraerlos, no porque sus ciudades produzcan gente distinta.
        """
        return 0.28 + 0.44 * self.professionalization_score

    @property
    def talent_spread(self) -> float:
        """Dispersión: las ligas modestas son más heterogéneas."""
        return 0.16 - 0.05 * self.professionalization_score


def resolve_markets(tree: PlaceTree, ruleset: RuleSet) -> list[MarketProfile]:
    """Resuelve en qué mercados concretos se pueden plantar clubes.

    Para una liga municipal baja a subzonas si el fixture las tiene; si no, usa
    la ciudad. Para alcances mayores usa ciudades.
    """
    candidates: list[Place] = []
    for key in ruleset.scope.place_keys:
        place = tree.get(key)
        if ruleset.scope.level is ScopeLevel.MUNICIPAL:
            districts = tree.children(key, PlaceKind.DISTRICT)
            candidates.extend(districts or [place])
        elif place.kind == PlaceKind.CITY:
            candidates.append(place)
        else:
            cities = tree.descendants(key, PlaceKind.CITY)
            candidates.extend(cities or [place])

    seen: set[str] = set()
    markets: list[MarketProfile] = []
    for place in candidates:
        if place.key in seen:
            continue
        seen.add(place.key)
        profile = tree.effective_profile(place.key)
        markets.append(
            MarketProfile(
                place_key=place.key,
                place_name=place.name,
                catchment_population=profile.population,
                economy_index=profile.economy_index,
                culture_index=profile.baseball_culture_index,
                infrastructure_index=profile.infrastructure_index,
                cost_of_living_index=profile.cost_of_living_index,
                confidence=profile.confidence,
                elevation_m=place.elevation_m,
                lat=place.lat,
                lon=place.lon,
            )
        )
    if not markets:
        raise ValueError("el territorio de la competición no contiene mercados utilizables")
    return sorted(markets, key=lambda m: m.place_key)


def build_context(tree: PlaceTree, ruleset: RuleSet, currency: str = "MXN") -> CompetitionContext:
    markets = resolve_markets(tree, ruleset)
    record = GenerationRecord(
        entity_kind="competition_context",
        entity_key=ruleset.name,
        procedure="build_context",
        procedure_version=PROCEDURE_VERSION,
        seed=0,
    )

    aggregate_population = sum(m.catchment_population for m in markets)
    # Promedio ponderado por población: un mercado de 2 millones pesa más que
    # una subzona de 200.000 al describir el ecosistema de la competición.
    total = float(aggregate_population) or 1.0
    economy = sum(m.economy_index * m.catchment_population for m in markets) / total
    culture = sum(m.culture_index * m.catchment_population for m in markets) / total
    infrastructure = sum(m.infrastructure_index * m.catchment_population for m in markets) / total
    pull = market_pull(aggregate_population)

    auto_score = _W_ECONOMY * economy + _W_MARKET * pull + _W_CULTURE * culture
    nudge = _SCOPE_NUDGE[ruleset.scope.level]
    contextual_score = max(0.0, min(1.0, auto_score + nudge))

    if ruleset.generation.professionalization is ContextualLevel.CONTEXTUAL_AUTO:
        prof_score = record.note(
            "professionalization_score",
            round(contextual_score, 4),
            Confidence.ESTIMATED,
            (
                f"contextual_auto: {_W_ECONOMY}*economía({economy:.3f}) + "
                f"{_W_MARKET}*mercado({pull:.3f}) + {_W_CULTURE}*cultura({culture:.3f}) "
                f"{nudge:+.2f} por alcance {ruleset.scope.level}"
            ),
            economy=round(economy, 4),
            market_pull=round(pull, 4),
            culture=round(culture, 4),
            scope_nudge=nudge,
        )
    else:
        prof_score = record.note(
            "professionalization_score",
            _EXPLICIT_LEVEL_SCORE[ruleset.generation.professionalization],
            Confidence.USER_CONFIGURED,
            f"el usuario fijó profesionalización={ruleset.generation.professionalization}",
            contextual_would_be=round(contextual_score, 4),
        )

    if ruleset.generation.economy is ContextualLevel.CONTEXTUAL_AUTO:
        economy_score = record.note(
            "economy_score",
            round(max(0.0, min(1.0, 0.6 * economy + 0.4 * pull)), 4),
            Confidence.ESTIMATED,
            "contextual_auto: 0.6*economía regional + 0.4*atracción de mercado",
            economy=round(economy, 4),
            market_pull=round(pull, 4),
        )
    else:
        economy_score = record.note(
            "economy_score",
            _EXPLICIT_LEVEL_SCORE[ruleset.generation.economy],
            Confidence.USER_CONFIGURED,
            f"el usuario fijó economía={ruleset.generation.economy}",
        )

    if ruleset.generation.institutional_maturity is ContextualLevel.CONTEXTUAL_AUTO:
        maturity_score = record.note(
            "maturity_score",
            round(max(0.0, min(1.0, 0.5 * infrastructure + 0.3 * culture + 0.2 * pull)), 4),
            Confidence.ESTIMATED,
            "contextual_auto: 0.5*infraestructura + 0.3*cultura + 0.2*mercado",
            infrastructure=round(infrastructure, 4),
        )
    else:
        maturity_score = record.note(
            "maturity_score",
            _EXPLICIT_LEVEL_SCORE[ruleset.generation.institutional_maturity],
            Confidence.USER_CONFIGURED,
            f"el usuario fijó madurez={ruleset.generation.institutional_maturity}",
        )

    tier = score_to_tier(prof_score)
    record.note(
        "professionalization_tier",
        str(tier),
        Confidence.ESTIMATED,
        f"umbrales fijos sobre el índice: {prof_score:.3f} cae en {tier}",
    )
    record.assumptions.append(
        "Los coeficientes de profesionalización y economía son heurísticos, no "
        "calibrados contra datos económicos reales."
    )
    if any(m.confidence is not Confidence.OBSERVED for m in markets):
        record.assumptions.append(
            "Al menos un mercado usa población o índices estimados/ficticios; la "
            "escala económica resultante hereda esa incertidumbre."
        )

    return CompetitionContext(
        ruleset_name=ruleset.name,
        scope_level=ruleset.scope.level,
        professionalization_score=float(prof_score),
        professionalization_tier=tier,
        economy_score=float(economy_score),
        maturity_score=float(maturity_score),
        aggregate_population=aggregate_population,
        eligible_markets=markets,
        currency=currency,
        record=record,
    )


def club_budget(
    market: MarketProfile,
    context: CompetitionContext,
    resource_multiplier: float,
) -> Decimal:
    """Presupuesto anual del club.

    `mercado^0.55 × economía local × nivel de la competición × desigualdad`.
    Heurística documentada, no una cifra observada.
    """
    units = Decimal(str(round((market.catchment_population / 1000.0) ** 0.55, 4)))
    local = Decimal(str(round(0.4 + 1.6 * market.economy_index, 4)))
    league = Decimal(str(round(0.2 + 6.0 * context.professionalization_score**2.2, 4)))
    spread = Decimal(str(round(resource_multiplier, 4)))
    value = _BUDGET_UNIT * units * local * league * spread
    return value.quantize(Decimal("1"))
