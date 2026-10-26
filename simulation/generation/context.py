"""Contexto de mercado: qué ofrece el territorio donde se juega.

Lo que este módulo **ya no hace** (FIX V2 de Fase 1, §7.2): producir un «nivel
de liga» que multiplique presupuestos. La causalidad va al revés:

```text
territorio + reglas  →  recursos locales finitos  →  cuentas de cada club
                                                  →  nivel efectivo de la competición
```

El `market_score` describe el entorno —economía, tamaño de mercado, cultura
deportiva— y sirve para repartir plazas y ponderar qué instituciones son
plausibles. El dinero lo calcula `simulation.economy` club por club, y el nivel
competitivo de la liga **emerge** de lo que esos clubes acabaron pudiendo
sostener (`effective_level`), no de una etiqueta elegida en un formulario.

Advertencia honesta: los coeficientes son **heurísticas sin calibrar** contra
datos económicos reales. Ver `docs/simulation-calibration.md`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal

from simulation.competitions.ruleset import (
    ParticipationModality,
    RuleSet,
    ScopeLevel,
)
from simulation.core.provenance import Confidence, GenerationRecord
from simulation.economy.model import ResourceTier, resource_tier
from simulation.geography.model import Place, PlaceKind, PlaceTree

PROCEDURE_VERSION = "context/1.1.0"

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


def market_pull(population: int) -> float:
    """Atracción de mercado en 0-1 a partir de la población captable.

    Logarítmica: duplicar habitantes no duplica el mercado deportivo.
    """
    if population <= 0:
        return 0.0
    return max(0.0, min(1.0, math.log10(population) / 7.0))


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
    modality: ParticipationModality
    #: Descripción del entorno, 0-1: economía, tamaño de mercado y cultura
    #: deportiva de los territorios elegidos. **No** es un nivel de riqueza de
    #: los clubes ni multiplica ningún importe.
    market_score: float
    aggregate_population: int
    eligible_markets: list[MarketProfile]
    #: Moneda de la jurisdicción. `None` si el territorio no tiene ancla.
    currency: str | None = None
    reference_monthly_cost: Decimal | None = None
    record: GenerationRecord = field(default=None)  # type: ignore[assignment]
    #: Nivel competitivo **emergente**: se fija después de generar los clubes,
    #: a partir de los recursos que de verdad pudieron sostener. Mientras no se
    #: calcule vale `None`, y nada que dependa de él puede ejecutarse antes.
    effective_level: float | None = None
    effective_tier: ResourceTier | None = None

    @property
    def level(self) -> float:
        """Nivel efectivo ya calculado. Falla si se pide antes de tiempo."""
        if self.effective_level is None:
            raise ValueError(
                "el nivel de la competición se calcula a partir de los recursos de "
                "sus clubes: no está disponible antes de generarlos"
            )
        return self.effective_level

    @property
    def talent_mean(self) -> float:
        """Centro de la distribución de habilidad que esta liga **atrae**, 0-1.

        No crea capacidades: una competición con más recursos atrae y retiene a
        mejores jugadores del mercado compartido porque puede ofrecerles más
        —compensación donde está permitida, instalaciones, exposición—. El
        origen de nadie modifica su techo (V2 §3.6).
        """
        return 0.28 + 0.44 * self.level

    @property
    def talent_spread(self) -> float:
        """Dispersión: las competiciones con menos recursos son más heterogéneas."""
        return 0.16 - 0.05 * self.level


def market_for_place(tree: PlaceTree, place_key: str) -> MarketProfile:
    """Perfil de mercado de un lugar concreto del árbol.

    Lo usa la generación para los mercados del alcance de la competición y el
    re-presupuesto de cada temporada para la zona en la que un club **ya** está,
    que puede no pertenecer al alcance de su competición actual: un club
    ascendido no se muda.
    """
    place = tree.get(place_key)
    profile = tree.effective_profile(place_key)
    return MarketProfile(
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


#: Cuán fino es cada nivel territorial. Sirve para no bajar más de lo que la
#: competición necesita: una liga nacional planta clubes en ciudades, no en
#: barrios, aunque los barrios estén en el árbol.
_GRANULARITY = {
    PlaceKind.COUNTRY: 0,
    PlaceKind.REGION: 1,
    PlaceKind.CITY: 2,
    PlaceKind.DISTRICT: 3,
}


def _markets_under(
    tree: PlaceTree,
    place: Place,
    finest: PlaceKind,
    seen: set[str],
    discarded: list[str],
) -> list[MarketProfile]:
    """Mercados utilizables dentro de un lugar, al nivel más fino que sirva.

    Desciende rama por rama, no por niveles completos: en un mismo país puede
    haber un estado con sus ciudades materializadas y otro del que solo se
    conoce el estado, y los dos tienen que poder acoger clubes.

    Un lugar entra como mercado cuando no hay nada utilizable por debajo y él
    tiene población. Si no la tiene, se descarta: la de su territorio padre no
    es la suya.
    """
    if _GRANULARITY[place.kind] < _GRANULARITY[finest]:
        finos: list[MarketProfile] = []
        for child in tree.children(place.key):
            if _GRANULARITY[child.kind] <= _GRANULARITY[finest]:
                finos.extend(_markets_under(tree, child, finest, seen, discarded))
        if finos:
            return finos

    if place.key in seen:
        return []
    seen.add(place.key)
    try:
        return [market_for_place(tree, place.key)]
    except KeyError:
        discarded.append(place.name)
        return []


def resolve_markets(tree: PlaceTree, ruleset: RuleSet) -> list[MarketProfile]:
    """Resuelve en qué mercados concretos se pueden plantar clubes.

    Baja al nivel más fino que de verdad sirva de cada territorio elegido:
    subzonas en una liga municipal, ciudades en cualquier otro alcance, y el
    propio territorio —un estado, un país— solo cuando no hay nada utilizable
    por debajo.

    Por qué ese orden: un país se usaba directamente como un único mercado en
    cuanto sus ciudades no estaban materializadas, y entonces los cuatro clubes
    de una liga nacional mexicana compartían la plaza «México» —el país entero
    como si fuera una ciudad—, con distancia de viaje cero entre ellos y los
    131 millones de habitantes repartidos entre los cuatro. Ahora el país es el
    último recurso, no el primero.
    """
    finest = PlaceKind.DISTRICT if ruleset.scope.level is ScopeLevel.MUNICIPAL else PlaceKind.CITY
    seen: set[str] = set()
    discarded: list[str] = []
    markets: list[MarketProfile] = []
    for key in ruleset.scope.place_keys:
        markets.extend(_markets_under(tree, tree.get(key), finest, seen, discarded))

    if not markets:
        detalle = f" (sin población utilizable: {', '.join(discarded)})" if discarded else ""
        raise ValueError(
            f"el territorio de la competición no contiene mercados utilizables{detalle}"
        )
    return sorted(markets, key=lambda m: m.place_key)


def build_context(
    tree: PlaceTree, ruleset: RuleSet, currency: str | None = None
) -> CompetitionContext:
    """Resuelve el entorno de la competición. **No** decide dinero ni nivel.

    `currency` solo se acepta para forzar una moneda en pruebas; lo normal es
    que salga del ancla monetaria del territorio.
    """
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
    pull = market_pull(aggregate_population)

    auto_score = _W_ECONOMY * economy + _W_MARKET * pull + _W_CULTURE * culture
    nudge = _SCOPE_NUDGE[ruleset.scope.level]
    market_score = record.note(
        "market_score",
        round(max(0.0, min(1.0, auto_score + nudge)), 4),
        Confidence.ESTIMATED,
        (
            f"{_W_ECONOMY}*economía({economy:.3f}) + {_W_MARKET}*mercado({pull:.3f}) + "
            f"{_W_CULTURE}*cultura({culture:.3f}) {nudge:+.2f} por alcance "
            f"{ruleset.scope.level}. Describe el entorno; no multiplica presupuestos"
        ),
        economy=round(economy, 4),
        market_pull=round(pull, 4),
        culture=round(culture, 4),
        scope_nudge=nudge,
    )

    # Moneda y ancla de la jurisdicción. Si el territorio no la tiene, se dice:
    # el motor no presume la moneda del idioma de la interfaz.
    anchor_key = ruleset.scope.place_keys[0]
    anchor = tree.economic_anchor(anchor_key)
    if currency is not None:
        resolved_currency: str | None = currency
        reference_cost = anchor.reference_monthly_cost if anchor else None
    elif anchor is not None:
        resolved_currency = anchor.currency
        reference_cost = anchor.reference_monthly_cost
        record.note(
            "currency",
            anchor.currency,
            anchor.confidence,
            (
                f"moneda de curso legal de la jurisdicción de {anchor_key}; coste "
                f"mensual de referencia {anchor.reference_monthly_cost} "
                f"({anchor.ref_year})"
            ),
            reference_monthly_cost=str(anchor.reference_monthly_cost),
        )
    else:
        resolved_currency = None
        reference_cost = None
        record.assumptions.append(
            f"La jurisdicción de {anchor_key} no tiene ancla monetaria declarada: los "
            "importes de sus instituciones quedan sin determinar en vez de inventarse."
        )

    record.note(
        "participation_modality",
        str(ruleset.participation_modality),
        Confidence.USER_CONFIGURED,
        (
            f"{ruleset.modality.description} Regla de compensación vigente: "
            f"{ruleset.effective_compensation_rule}"
        ),
    )
    record.assumptions.append(
        "El índice de mercado es una heurística sin calibrar. Describe el entorno "
        "y reparte plazas; ningún importe se deriva de él."
    )
    if any(m.confidence is not Confidence.OBSERVED for m in markets):
        record.assumptions.append(
            "Al menos un mercado usa población o índices estimados/ficticios; las "
            "cuentas de sus clubes heredan esa incertidumbre."
        )

    return CompetitionContext(
        ruleset_name=ruleset.name,
        scope_level=ruleset.scope.level,
        modality=ruleset.participation_modality,
        market_score=float(market_score),
        aggregate_population=aggregate_population,
        eligible_markets=markets,
        currency=resolved_currency,
        reference_monthly_cost=reference_cost,
        record=record,
    )


#: Divisor de la función que traduce recursos en nivel de juego:
#: `nivel = log10(meses_de_coste_de_referencia + 1) / LEVEL_SCALE`.
#:
#: No es un número arbitrario: es una **función de transferencia calibrada**
#: contra las bandas del propio motor de partidos. Se fija con un punto de
#: anclaje: una liga nacional profesional, cuyos clubes reúnen del orden de 100
#: meses de gasto doméstico de su país, tiene que caer en 0.68, que es el nivel
#: al que `LeagueRates` reproduce béisbol de calidad profesional. De ahí
#: `log10(103) / 0.68 ≈ 2.96`. Una liga llanera de barrio, con 6-15 meses, cae
#: en torno a 0.34 con la misma función.
#:
#: Depende del fixture con el que se calibró; si cambian las anclas monetarias
#: o los coeficientes de coste, hay que volver a medirlo con
#: `make calibrate`. Ver `docs/simulation-calibration.md`.
LEVEL_SCALE = 2.96


def resolve_effective_level(
    context: CompetitionContext,
    operating_budgets_in_months: list[float],
) -> CompetitionContext:
    """Fija el nivel competitivo a partir de lo que los clubes pudieron sostener.

    Es el paso que invierte la causalidad: el nivel **sale** del dinero que las
    instituciones reunieron de verdad, no al contrario. La escala es logarítmica
    sobre meses de coste de referencia, porque duplicar el presupuesto no
    duplica la calidad del juego.
    """
    if not operating_budgets_in_months:
        context.effective_level = round(0.25 + 0.3 * context.market_score, 4)
        context.effective_tier = None
        return context

    ordered = sorted(operating_budgets_in_months)
    median = ordered[len(ordered) // 2]
    # 1 mes → 0.10; 10 → 0.33; 100 → 0.67; 1000 → 1.0
    level = math.log10(max(1.0, median) + 1.0) / LEVEL_SCALE
    context.effective_level = round(max(0.05, min(1.0, level)), 4)
    context.effective_tier = resource_tier(median)
    if context.record is not None:
        context.record.note(
            "effective_level",
            context.effective_level,
            Confidence.ESTIMATED,
            (
                f"log10(mediana de presupuesto en meses de coste de referencia = "
                f"{median:.1f}) / {LEVEL_SCALE} sobre {len(ordered)} clubes ya "
                f"generados. "
                f"Nivel de recursos resultante: {context.effective_tier}"
            ),
            median_months=round(median, 2),
            min_months=round(ordered[0], 2),
            max_months=round(ordered[-1], 2),
        )
    return context
