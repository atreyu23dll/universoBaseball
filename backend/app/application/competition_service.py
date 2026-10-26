"""Casos de uso de competiciones: crear, previsualizar y generar el mundo.

El punto de este archivo: el usuario define reglas y el motor produce
instituciones. Nada aquí crea ligas inferiores, filiales ni pirámides por su
cuenta; una competición nueva nace **independiente** y solo se vincula si el
usuario crea la relación.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application import education_service, geography_service, organization_service
from app.application.errors import (
    ConflictError,
    NotFoundError,
    TypedValidationFailure,
    ValidationFailure,
)
from app.application.mappers import venue_dimensions_to_json
from app.application.universe_service import get_universe, record_event
from app.infrastructure import models as m
from simulation import SIM_VERSION
from simulation.competitions.ruleset import RelationshipMode, RuleSet, parse_ruleset
from simulation.core.errors import RuleValidationError, ScheduleError
from simulation.core.events import EventType, SimulationEvent
from simulation.core.provenance import Confidence, GenerationRecord
from simulation.economy.model import GovernanceModel
from simulation.generation.context import build_context
from simulation.generation.world import generate_competition_world
from simulation.geography.geonames import ATTRIBUTION as GEONAMES_ATTRIBUTION
from simulation.geography.geonames import normalize as geonames_normalize
from simulation.geography.model import (
    EconomicAnchor,
    Place,
    PlaceKind,
    PlaceTree,
    RegionProfile,
)


def load_place_tree(session: Session, universe_id: str) -> PlaceTree:
    """Reconstruye el árbol geográfico del universo desde la base."""
    rows = session.scalars(select(m.Place).where(m.Place.universe_id == universe_id)).all()
    profiles = {
        row.place_id: row
        for row in session.scalars(
            select(m.RegionProfile).where(m.RegionProfile.universe_id == universe_id)
        ).all()
    }
    by_id = {row.id: row for row in rows}
    tree = PlaceTree()
    for row in rows:
        profile_row = profiles.get(row.id)
        profile = None
        if profile_row is not None:
            profile = RegionProfile(
                ref_year=profile_row.ref_year,
                population=profile_row.population,
                economy_index=profile_row.economy_index,
                baseball_culture_index=profile_row.baseball_culture_index,
                cost_of_living_index=profile_row.cost_of_living_index,
                infrastructure_index=profile_row.infrastructure_index,
                confidence=Confidence(profile_row.confidence),
                sources=tuple(profile_row.sources),
            )
        parent_key = by_id[row.parent_id].place_key if row.parent_id else None
        anchor = None
        if row.economy:
            anchor = EconomicAnchor(
                currency=str(row.economy["currency"]),
                reference_monthly_cost=Decimal(str(row.economy["reference_monthly_cost"])),
                ref_year=int(row.economy["ref_year"]),
                confidence=Confidence(row.economy.get("confidence", "estimated")),
                sources=tuple(row.economy.get("sources", ())),
            )
        tree.places[row.place_key] = Place(
            key=row.place_key,
            kind=PlaceKind(row.kind),
            name=row.name,
            country_code=row.country_code,
            timezone=row.timezone,
            lat=row.lat,
            lon=row.lon,
            parent_key=parent_key,
            elevation_m=row.elevation_m,
            confidence=Confidence(row.confidence),
            sources=tuple(row.sources),
            profile=profile,
            economy=anchor,
        )
    return tree


#: Campos de elección institucional que el formulario no puede enviar nunca
#: (FIX V2 §10.1). Se rechazan con un código propio y una explicación de a quién
#: le corresponde esa decisión, en vez de aceptarlos y esconderlos.
DEPRECATED_CLUB_FIELDS = {
    "professionalization": "el nivel de profesionalización de los clubes",
    "economy": "la intensidad económica de los clubes",
    "institutional_maturity": "la madurez institucional de los clubes",
    "club_budget": "el presupuesto de los clubes",
    "club_wealth_tier": "el nivel de riqueza de los clubes",
    "club_owner_type": "el tipo de propietario",
    "club_organization_type": "la forma de organización",
    "club_labor_model": "el modelo laboral",
    "club_staff_size": "el tamaño de la plantilla administrativa",
    "club_stadium_ownership": "la propiedad del estadio",
    "club_financing_source": "la fuente de financiación",
    "club_sponsor_count": "el número de patrocinadores",
    "club_player_talent_tier": "el nivel de talento de los jugadores",
    "club_governance_model": "el modelo de gobierno",
    "organization_policy": "la política de organización",
    "resource_policy": "la política de recursos",
    "venue_policy": "la política de instalaciones",
    "staffing_policy": "la política de personal",
}


def _reject_deprecated_fields(payload: dict) -> None:
    """Rechaza los campos de la adenda V1 con un error tipado."""
    encontrados: list[str] = []
    for campo in DEPRECATED_CLUB_FIELDS:
        if campo in payload:
            encontrados.append(campo)
        if campo in (payload.get("generation") or {}):
            encontrados.append(f"generation.{campo}")
    if not encontrados:
        return
    descripciones = ", ".join(
        f"`{campo}` ({DEPRECATED_CLUB_FIELDS[campo.split('.')[-1]]})" for campo in encontrados
    )
    raise TypedValidationFailure(
        "DEPRECATED_CLUB_GENERATION_FIELD",
        (
            f"Estos campos ya no existen en la creación de competiciones: {descripciones}. "
            "El usuario define la competición; cómo se organiza y cuánto dinero reúne "
            "cada institución lo decide ella según su entorno."
        ),
        [
            "quita esos campos de la petición",
            "si lo que quieres es una exigencia del reglamento, úsala como tal: "
            "`admission` para requisitos de participación y `financial_regulations` "
            "para normas de pago",
            "la única pregunta de naturaleza institucional es `participation_modality`",
        ],
    )


def validate_ruleset(
    payload: dict, session: Session | None = None, universe_id: str | None = None
) -> RuleSet:
    _reject_deprecated_fields(payload)
    try:
        ruleset = parse_ruleset(payload)
    except Exception as exc:  # pydantic ValidationError u otro
        raise ValidationFailure(f"el reglamento no es válido: {exc}") from exc
    if session is not None and universe_id is not None:
        return education_service.canonicalize_school_universities(session, universe_id, ruleset)
    return ruleset


def resolve_ruleset_territory(
    session: Session, universe: m.Universe, ruleset: RuleSet, persist: bool = False
) -> tuple[RuleSet, PlaceTree, list[str]]:
    """Resuelve el territorio del reglamento y devuelve el árbol con el que simular.

    `persist=False` —lo que usa la previsualización— resuelve las entidades del
    gazetteer **en memoria**: el árbol sale completo y utilizable, y el mundo no
    se toca. Es el caso T01 del FIX V2: previsualizar no puede escribir nada.

    `persist=True` —lo que usa la confirmación— escribe esos lugares en el
    universo, con sus ancestros, su población y el ancla monetaria de su país,
    porque desde ese momento forman parte de la partida.

    Los dos caminos calculan lo mismo con el mismo código, así que lo que se
    previsualiza es lo que se crea.
    """
    avisos: list[str] = []
    claves = list(ruleset.scope.place_keys)
    tree = load_place_tree(session, universe.id)

    if ruleset.scope.entity_ids:
        resumen = geography_service.resolve_territory(session, ruleset.scope.entity_ids)
        avisos.extend(resumen["warnings"])
        if persist:
            nuevas = materialize_territory(session, universe, ruleset.scope.entity_ids)
            tree = load_place_tree(session, universe.id)
        else:
            nuevas = _graft_territory(session, universe, tree, ruleset.scope.entity_ids)
        claves = list(dict.fromkeys(claves + nuevas))
        ruleset = ruleset.model_copy(
            update={"scope": ruleset.scope.model_copy(update={"place_keys": claves})}
        )

    _check_territory(tree, ruleset)
    return ruleset, tree, avisos


def _market_divisions(session: Session, entidad: m.GazetteerEntity) -> list[m.GazetteerEntity]:
    """Divisiones de primer nivel de un país, que son sus mercados reales.

    Elegir un país como territorio no debería plantar todos los clubes de una
    liga nacional en una única plaza llamada «México» con 131 millones de
    habitantes: eso daba viajes de cero kilómetros entre clubes y una sola bolsa
    de recursos para todos. Las divisiones se traen al árbol **sin** entrar en
    el alcance declarado por el usuario; `resolve_markets` las encuentra como
    descendientes y las prefiere al país.

    Solo se expande un país. Una región elegida a mano sigue siendo un mercado:
    quien escoge Sonora quiere Sonora, no sus 72 municipios.
    """
    if entidad.kind != "country":
        return []
    return list(
        session.scalars(
            select(m.GazetteerEntity)
            .where(
                m.GazetteerEntity.country_iso2 == entidad.country_iso2,
                m.GazetteerEntity.kind == "region",
                m.GazetteerEntity.feature_code == "ADM1",
            )
            .order_by(m.GazetteerEntity.name)
        ).all()
    )


def _graft_territory(
    session: Session,
    universe: m.Universe,
    tree: PlaceTree,
    entity_ids: list[str],
) -> list[str]:
    """Injerta entidades del gazetteer en el árbol **sin escribir en la base**.

    Mismo resultado que `materialize_territory`, en memoria: el árbol queda con
    el lugar, sus ancestros, su perfil y el ancla monetaria de su país, listo
    para generar un mundo que después se descarta.
    """
    claves: list[str] = []
    for entity_id in entity_ids:
        entidad = geography_service.get_entity(session, entity_id)
        claves.append(_graft_place(session, universe, tree, entidad))
        for division in _market_divisions(session, entidad):
            _graft_place(session, universe, tree, division)
    return claves


def _graft_profile(
    session: Session,
    universe: m.Universe,
    entidad: m.GazetteerEntity,
    pais: m.GazetteerCountry | None,
) -> RegionProfile | None:
    """Perfil en memoria de una entidad del gazetteer, o `None` sin población.

    Es el gemelo de `_ensure_profile` para el camino que no escribe en la base.
    Los dos tienen que decidir lo mismo: lo que se previsualiza es lo que se
    crea.
    """
    poblacion, fuente_poblacion = _population_of(session, entidad, pais)
    if not poblacion:
        return None
    curado = _curated_indices(session, universe, entidad)
    if curado is not None:
        indices, fuentes, confianza = curado
    else:
        indices, fuentes, confianza = _neutral_indices()
    return RegionProfile(
        ref_year=2025,
        population=int(poblacion),
        confidence=Confidence(confianza),
        sources=(GEONAMES_ATTRIBUTION, fuente_poblacion, *tuple(fuentes)),
        **indices,
    )


def _population_of(
    session: Session,
    entidad: m.GazetteerEntity,
    pais: m.GazetteerCountry | None,
) -> tuple[int, str]:
    """Población de una entidad y de dónde sale, para escribirlo en el perfil.

    Una división administrativa llega de GeoNames sin población propia —la
    fuente no la publica— y la suya es la de sus localidades. Sin este paso el
    lugar se quedaba sin perfil y heredaba el del país: cada estado mexicano
    pasaba a tener 131,9 millones de habitantes.
    """
    poblacion = entidad.population or (pais.population if entidad.kind == "country" and pais else 0)
    if poblacion:
        return int(poblacion), f"población: {entidad.source} {entidad.source_id}"
    poblacion, localidades = geography_service.aggregated_population(session, entidad)
    return int(poblacion), (
        f"población: {localidades} localidades de {entidad.name} presentes en el "
        f"gazetteer ({entidad.source}), agregadas por municipio para no contar dos "
        "veces una ciudad y sus secciones; la fuente no publica población propia "
        "para divisiones administrativas, así que la cifra es parcial y depende de "
        "qué localidades se importaron"
    )


def _neutral_indices() -> tuple[dict[str, float], list[str], str]:
    """Supuesto declarado para un territorio sin índices conocidos."""
    return (
        {
            "economy_index": 0.5,
            "baseball_culture_index": 0.5,
            "cost_of_living_index": 0.5,
            "infrastructure_index": 0.5,
        },
        [
            "índices: supuesto neutral declarado, sin evidencia local de "
            "economía, cultura beisbolística ni infraestructura deportiva"
        ],
        str(Confidence.SCENARIO_ASSUMPTION),
    )


def _graft_place(
    session: Session,
    universe: m.Universe,
    tree: PlaceTree,
    entidad: m.GazetteerEntity,
) -> str:
    clave = f"{entidad.source}:{entidad.source_id}"
    existente = tree.places.get(clave)
    if existente is not None:
        if existente.profile is None:
            # El lugar entró al universo antes de que las divisiones
            # administrativas tuvieran población: sin perfil heredaría el del
            # país. Se le da el suyo aquí también, o previsualizar y crear
            # dejarían de coincidir.
            perfil = _graft_profile(
                session, universe, entidad, session.get(m.GazetteerCountry, entidad.country_iso2)
            )
            if perfil is not None:
                tree.places[clave] = replace(existente, profile=perfil)
        return clave

    padre_clave: str | None = None
    if entidad.parent_id:
        padre = session.get(m.GazetteerEntity, entidad.parent_id)
        if padre is not None:
            padre_clave = _graft_place(session, universe, tree, padre)

    pais = session.get(m.GazetteerCountry, entidad.country_iso2)
    ancla = None
    if (
        entidad.kind == "country"
        and pais is not None
        and pais.currency_code
        and pais.reference_monthly_cost is not None
    ):
        ancla = EconomicAnchor(
            currency=pais.currency_code,
            reference_monthly_cost=Decimal(pais.reference_monthly_cost),
            ref_year=pais.reference_cost_year or 2025,
            confidence=Confidence.ESTIMATED,
            sources=(GEONAMES_ATTRIBUTION, "ISO 4217", *tuple(pais.reference_cost_sources)),
        )

    perfil = _graft_profile(session, universe, entidad, pais)

    tree.places[clave] = Place(
        key=clave,
        kind=PlaceKind(entidad.kind),
        name=entidad.name,
        country_code=entidad.country_iso2,
        timezone=entidad.timezone or "UTC",
        lat=entidad.lat,
        lon=entidad.lon,
        parent_key=padre_clave,
        elevation_m=entidad.elevation_m,
        confidence=Confidence.OBSERVED,
        sources=(GEONAMES_ATTRIBUTION, f"{entidad.source} {entidad.source_id}"),
        profile=perfil,
        economy=ancla,
    )
    return clave


def _governance_of(club: Any) -> GovernanceModel:
    """La forma de gobierno que el motor decidió para este club.

    Sale de la organización que el club se dio al generarse, no de una elección
    del usuario: el formulario no puede pedirla (FIX V2 §1.2).
    """
    organizacion = getattr(club, "organization", None)
    if organizacion is None:
        return GovernanceModel.COLLECTIVE
    return GovernanceModel(str(organizacion.governance))


def _place_ids_of(session: Session, universe_id: str) -> dict[str, str]:
    return {
        row.place_key: row.id
        for row in session.scalars(select(m.Place).where(m.Place.universe_id == universe_id)).all()
    }


def preview_generation(session: Session, universe_id: str, payload: dict) -> dict:
    """Previsualiza sin crear nada. Se puede repetir con otra semilla."""
    universe = get_universe(session, universe_id)
    ruleset = validate_ruleset(payload, session, universe_id)
    # `persist=False`: previsualizar no escribe en el mundo (caso T01).
    ruleset, tree, territory_warnings = resolve_ruleset_territory(
        session, universe, ruleset, persist=False
    )

    seed = ruleset.effective_seed(universe.master_seed)
    world = generate_competition_world(
        tree=tree,
        ruleset=ruleset,
        master_seed=seed,
        edition_key=f"preview:{ruleset.checksum()[:12]}",
        world_date=universe.world_date,
    )
    context = world.context

    # La previsualización muestra lo que el **motor** decidió para cada
    # institución —gobierno, sede, cuentas con su desglose— y no ofrece ningún
    # control para cambiarlo: el usuario puede validar o regenerar, no editar
    # club por club (FIX V2 §1.4).
    clubs_preview = [
        {
            "name": club.name,
            "place": next(
                m_.place_name
                for m_ in context.eligible_markets
                if m_.place_key == club.home_place_key
            ),
            "institutional_type": str(club.institutional_type),
            "governance": str(club.organization.governance) if club.organization else None,
            "has_owner": club.organization.has_owner if club.organization else None,
            "venue_usage": str(club.organization.venue_agreement) if club.organization else None,
            "roles": (
                [role.as_dict() for role in club.organization.roles] if club.organization else []
            ),
            "annual_budget": str(club.finances.annual_budget),
            "financial_assessment": (
                club.finances.profile.as_dict() if club.finances.profile else None
            ),
            "venue_name": club.venue.name,
            "venue_type": str(club.venue.venue_type),
            "capacity": club.venue.capacity,
            "fan_base": club.fan_base,
            "resource_multiplier": club.resource_multiplier,
            "primary_color": club.brand.primary_color,
            "secondary_color": club.brand.secondary_color,
            # División en la que jugaría, con el motivo del reparto. Vacío si la
            # competición es de tabla única.
            "group": world.group_of.get(club.key, ""),
            "group_reason": next(
                (p.reason for p in world.groups if p.club_key == club.key),
                "",
            ),
        }
        for club in world.clubs
    ]
    budgets = sorted(int(c.finances.annual_budget) for c in world.clubs)
    return {
        "ruleset_checksum": ruleset.checksum(),
        "seed": seed,
        "context": {
            "participation_modality": str(ruleset.participation_modality),
            "education_track": (
                str(ruleset.education.track) if ruleset.education is not None else None
            ),
            "participants_source": (
                "universidades reales del catálogo territorial"
                if ruleset.requires_real_universities
                else None
            ),
            "modality_description": ruleset.modality.description,
            "compensation_rule": str(ruleset.effective_compensation_rule),
            "market_score": round(context.market_score, 4),
            "effective_level": context.effective_level,
            "resource_tier": str(context.effective_tier) if context.effective_tier else None,
            "aggregate_population": context.aggregate_population,
            "currency": context.currency,
            "reference_monthly_cost": (
                str(context.reference_monthly_cost) if context.reference_monthly_cost else None
            ),
            "talent_mean": round(context.talent_mean, 4),
            "markets": [
                {
                    "place_key": market.place_key,
                    "name": market.place_name,
                    "population": market.catchment_population,
                    "economy_index": market.economy_index,
                    "culture_index": market.culture_index,
                    "training_opportunity": round(market.training_opportunity, 4),
                    "confidence": str(market.confidence),
                }
                for market in context.eligible_markets
            ],
        },
        "clubs": clubs_preview,
        "budget_range": {
            "min": budgets[0],
            "median": budgets[len(budgets) // 2],
            "max": budgets[-1],
        },
        "people_generated": len(world.people),
        "free_agents": len(world.free_agents),
        "schedule": {
            "games": len(world.schedule.games),
            "games_per_club": world.schedule.games_per_club,
            "requested_games_per_club": world.schedule.requested_games_per_club,
            "adjusted": world.schedule.adjusted,
            "first_date": world.schedule.first_date,
            "last_date": world.schedule.last_date,
            "intra_group_games": sum(1 for game in world.schedule.games if game.matchup == "intra"),
            "inter_group_games": sum(1 for game in world.schedule.games if game.matchup == "inter"),
        },
        "structure": (
            {
                "count": ruleset.structure.count,
                "assignment": str(ruleset.structure.assignment),
                "intra_cycles": ruleset.structure.intra_cycles,
                "inter_cycles": ruleset.structure.inter_cycles,
                "qualifiers_per_group": ruleset.structure.qualifiers_per_group,
                "wildcards": ruleset.structure.wildcards,
                "groups": [
                    {
                        "label": etiqueta,
                        "clubs": sum(1 for p in world.groups if p.group_key == etiqueta),
                    }
                    for etiqueta in ruleset.structure.labels
                ],
            }
            if ruleset.structure.has_groups
            else None
        ),
        "warnings": territory_warnings + world.warnings + _viability_warnings(ruleset, world),
        "provenance": [record.as_dict() for record in world.records[:2]],
    }


def _viability_warnings(ruleset: RuleSet, world) -> list[str]:
    """Advierte de mundos materialmente inverosímiles, sin prohibirlos.

    La especificación pide avisar, no vetar: un universo experimental es
    legítimo mientras el usuario sepa lo que está pidiendo. Lo que se mira aquí
    son los **resultados** del generador —clubes en déficit, instalaciones
    insuficientes, mercados sin datos—, no etiquetas del formulario.
    """
    warnings: list[str] = []
    context = world.context
    per_club = context.aggregate_population / max(1, ruleset.generation.club_count)
    if per_club < 25_000:
        warnings.append(
            f"Cada club tendría un mercado de unos {per_club:,.0f} habitantes. "
            "Es poca base social para sostener tantas plantillas en el mismo territorio."
        )

    if context.currency is None:
        warnings.append(
            "Esta jurisdicción no tiene ancla monetaria en los datos disponibles: las "
            "cuentas de los clubes quedan sin cuantificar en vez de inventarse."
        )

    perfiles = [c.finances.profile for c in world.clubs if c.finances.profile is not None]
    en_deficit = [p for p in perfiles if p.balance is not None and p.balance < 0]
    if en_deficit:
        warnings.append(
            f"{len(en_deficit)} de {len(perfiles)} clubes no cubren sus obligaciones con "
            "los ingresos que su entorno permite. Pueden recortar, endeudarse o acabar "
            "retirándose: el motor no les regala dinero para completar la competición."
        )
    riesgos = {riesgo for p in perfiles for riesgo in p.risks}
    warnings.extend(sorted(riesgos))

    if perfiles:
        meses = sorted(
            p.months_of_reference_cost for p in perfiles if p.months_of_reference_cost is not None
        )
        if meses and meses[0] > 0 and meses[-1] / meses[0] > 12:
            warnings.append(
                f"La desigualdad entre clubes es grande: del más modesto al mayor hay "
                f"{meses[-1] / meses[0]:.0f} veces de diferencia en presupuesto. Es "
                "posible, pero conviene revisar si el territorio lo justifica."
            )

    if (
        ruleset.season.games_per_club_target
        / max(0.5, ruleset.modality.sustainable_games_per_week)
        / 4.3
        > 10
    ):
        warnings.append(
            f"{ruleset.season.games_per_club_target} partidos por club a "
            f"{ruleset.modality.sustainable_games_per_week} por semana ocuparían casi todo "
            "el año. Revisa el calendario o la modalidad."
        )
    return warnings


def _check_territory(tree: PlaceTree, ruleset: RuleSet) -> None:
    """Comprueba que el territorio está resuelto en este universo.

    Una clave que no existe no es un error de escritura cualquiera: es un
    territorio **sin resolver**, y se devuelve con su código propio para que la
    interfaz pueda mandar al usuario a buscar el lugar en vez de dejarle
    adivinar (FIX V2 §13 y §10.4, caso T07).
    """
    missing = [key for key in ruleset.scope.place_keys if key not in tree.places]
    if missing:
        raise TypedValidationFailure(
            "GEOGRAPHY_UNRESOLVED",
            f"el territorio no está resuelto: {missing} no son lugares de este universo",
            [
                "busca el lugar con GET /api/v1/geography/search y usa el "
                "identificador que devuelve en `scope.entity_ids`",
                "un nombre escrito a mano no sirve como territorio",
                "o consulta /api/v1/universes/{id}/geography para ver las claves curadas",
            ],
        )
    countries = {
        tree.places[key].country_code for key in ruleset.scope.place_keys if key in tree.places
    }
    if ruleset.scope.level.value == "multinational":
        if len(countries) < 2:
            raise TypedValidationFailure(
                "GEOGRAPHY_UNRESOLVED",
                "una competición internacional de clubes necesita al menos dos países",
                ["elige dos o más países en el globo territorial"],
            )
    elif len(countries) > 1:
        # Una liga regional puede abarcar varios estados —el norte de México es
        # un territorio deportivo real— pero sigue siendo de una jurisdicción:
        # su moneda, su calendario y sus reglas salen de un solo país. Cruzar la
        # frontera es otra cosa, y tiene su propio alcance.
        raise TypedValidationFailure(
            "GEOGRAPHY_UNRESOLVED",
            "los territorios de esta competición están en países distintos: "
            f"{', '.join(sorted(countries))}",
            [
                "elige territorios de un mismo país",
                "si la competición cruza fronteras, su alcance es internacional",
            ],
        )


def materialize_territory(
    session: Session, universe: m.Universe, entity_ids: list[str]
) -> list[str]:
    """Trae entidades del gazetteer mundial al universo y devuelve sus claves.

    El universo tiene su propia copia de la geografía —así una partida puede
    calibrar los índices de un mercado sin tocar las demás—, y esta función es el
    puente: crea el lugar, **sus ancestros** para que la jerarquía funcione, su
    perfil regional con la población de la fuente, y el ancla monetaria del país.

    Lo que **no** hace: inventar índices socioeconómicos. Un territorio que no
    esté en el fixture curado recibe un supuesto neutral marcado como tal, nunca
    un número deducido del país.
    """
    if not entity_ids:
        return []

    existentes = {
        row.gazetteer_entity_id: row
        for row in session.scalars(
            select(m.Place).where(
                m.Place.universe_id == universe.id, m.Place.gazetteer_entity_id.is_not(None)
            )
        ).all()
        if row.gazetteer_entity_id
    }
    por_clave = {
        row.place_key: row
        for row in session.scalars(select(m.Place).where(m.Place.universe_id == universe.id)).all()
    }
    claves: list[str] = []

    for entity_id in entity_ids:
        entidad = geography_service.get_entity(session, entity_id)
        fila = existentes.get(entidad.id)
        if fila is None:
            fila = _ensure_place(session, universe, entidad, existentes, por_clave)
        else:
            _fill_missing_profile(session, universe, entidad, fila)
        claves.append(fila.place_key)
        for division in _market_divisions(session, entidad):
            ya = existentes.get(division.id)
            if ya is None:
                _ensure_place(session, universe, division, existentes, por_clave)
            else:
                _fill_missing_profile(session, universe, division, ya)
    session.flush()
    return claves


def _ensure_place(
    session: Session,
    universe: m.Universe,
    entidad: m.GazetteerEntity,
    existentes: dict[str, m.Place],
    por_clave: dict[str, m.Place],
) -> m.Place:
    """Crea el lugar y, recursivamente, sus ancestros."""
    if entidad.id in existentes:
        return existentes[entidad.id]

    padre_fila: m.Place | None = None
    if entidad.parent_id:
        padre = session.get(m.GazetteerEntity, entidad.parent_id)
        if padre is not None:
            padre_fila = _ensure_place(session, universe, padre, existentes, por_clave)

    clave = f"{entidad.source}:{entidad.source_id}"
    if clave in por_clave:
        fila = por_clave[clave]
        fila.gazetteer_entity_id = entidad.id
        existentes[entidad.id] = fila
        return fila

    pais = session.get(m.GazetteerCountry, entidad.country_iso2)
    ancla = None
    if (
        entidad.kind == "country"
        and pais is not None
        and pais.currency_code
        and pais.reference_monthly_cost is not None
    ):
        ancla = {
            "currency": pais.currency_code,
            "reference_monthly_cost": str(pais.reference_monthly_cost),
            "ref_year": pais.reference_cost_year or 2025,
            "confidence": "estimated",
            "sources": [GEONAMES_ATTRIBUTION, "ISO 4217", *list(pais.reference_cost_sources)],
        }

    fila = m.Place(
        universe_id=universe.id,
        place_key=clave,
        kind=entidad.kind,
        name=entidad.name,
        country_code=entidad.country_iso2,
        timezone=entidad.timezone or "UTC",
        lat=entidad.lat,
        lon=entidad.lon,
        elevation_m=entidad.elevation_m,
        parent_id=padre_fila.id if padre_fila is not None else None,
        confidence=str(Confidence.OBSERVED),
        sources=[GEONAMES_ATTRIBUTION, f"{entidad.source} {entidad.source_id}"],
        economy=ancla,
        gazetteer_entity_id=entidad.id,
    )
    session.add(fila)
    session.flush()
    existentes[entidad.id] = fila
    por_clave[clave] = fila

    _ensure_profile(session, universe, entidad, fila, pais)
    return fila


def _fill_missing_profile(
    session: Session,
    universe: m.Universe,
    entidad: m.GazetteerEntity,
    fila: m.Place,
) -> None:
    """Da perfil a un lugar que ya estaba en el universo y no tenía ninguno.

    Cura universos creados antes de que las divisiones administrativas tuvieran
    población: sus regiones entraron sin perfil y heredaban el del país, de modo
    que cada estado se simulaba con los habitantes de toda su jurisdicción. La
    próxima vez que se usen como territorio quedan arregladas, sin migración y
    sin tocar lo que ya tenía perfil propio: un mercado calibrado a mano no se
    sobrescribe.
    """
    existe = session.scalars(
        select(m.RegionProfile).where(
            m.RegionProfile.universe_id == universe.id,
            m.RegionProfile.place_id == fila.id,
        )
    ).first()
    if existe is not None:
        return
    pais = session.get(m.GazetteerCountry, entidad.country_iso2)
    _ensure_profile(session, universe, entidad, fila, pais)


def _ensure_profile(
    session: Session,
    universe: m.Universe,
    entidad: m.GazetteerEntity,
    fila: m.Place,
    pais: m.GazetteerCountry | None,
) -> None:
    """Perfil regional del lugar: población con fuente, índices como supuesto.

    Comparte con `_graft_profile` cómo se resuelven población e índices, para
    que el camino que escribe en la base y el que solo previsualiza no puedan
    separarse. Si no hay población —ni propia ni agregada de sus localidades—,
    el lugar queda **sin perfil** y `effective_profile` lo rechazará como
    mercado, en vez de darle la de su país.
    """
    poblacion, fuente_poblacion = _population_of(session, entidad, pais)
    if not poblacion:
        return

    # Si este lugar ya estaba calibrado a mano en el universo, sus índices
    # valen más que un supuesto neutral: buscar un sitio en el gazetteer no
    # puede dar peores datos que tenerlo en el fixture curado.
    curado = _curated_indices(session, universe, entidad)
    if curado is not None:
        indices, fuentes, confianza = curado
    else:
        indices, fuentes, confianza = _neutral_indices()

    session.add(
        m.RegionProfile(
            universe_id=universe.id,
            place_id=fila.id,
            ref_year=2025,
            population=int(poblacion),
            confidence=confianza,
            sources=[GEONAMES_ATTRIBUTION, fuente_poblacion, *fuentes],
            **indices,
        )
    )


def _curated_indices(
    session: Session, universe: m.Universe, entidad: m.GazetteerEntity
) -> tuple[dict[str, float], list[str], str] | None:
    """Índices del fixture curado para este lugar, si existe uno equivalente.

    El fixture es anterior al gazetteer y no tiene `geonameid`, así que la
    correspondencia se hace por nombre normalizado y país. Es una heurística y
    se declara como tal en las fuentes del perfil.
    """
    objetivo = geonames_normalize(entidad.name)
    for lugar in session.scalars(
        select(m.Place).where(
            m.Place.universe_id == universe.id,
            m.Place.country_code == entidad.country_iso2,
            m.Place.gazetteer_entity_id.is_(None),
        )
    ).all():
        if geonames_normalize(lugar.name) != objetivo:
            continue
        perfil = session.scalars(
            select(m.RegionProfile).where(m.RegionProfile.place_id == lugar.id)
        ).first()
        if perfil is None:
            continue
        return (
            {
                "economy_index": perfil.economy_index,
                "baseball_culture_index": perfil.baseball_culture_index,
                "cost_of_living_index": perfil.cost_of_living_index,
                "infrastructure_index": perfil.infrastructure_index,
            },
            [
                f"índices: del fixture curado de «{lugar.name}», emparejado por "
                "nombre y país con la entidad del gazetteer",
                *list(perfil.sources),
            ],
            perfil.confidence,
        )
    return None


def create_competition(
    session: Session, universe_id: str, payload: dict
) -> m.CompetitionDefinition:
    universe = get_universe(session, universe_id)
    ruleset = validate_ruleset(payload, session, universe_id)
    ruleset, tree, _ = resolve_ruleset_territory(session, universe, ruleset, persist=True)

    # Una competición no puede nacer dependiente: la dependencia la crea una
    # relación explícita, y mientras no exista no hay a quién depender. Marcarla
    # aquí dejaría una competición «dependiente» sin superior, que es un estado
    # que no significa nada.
    if ruleset.relationship_mode is not RelationshipMode.INDEPENDENT:
        raise ValidationFailure(
            f"«{ruleset.name}» no puede crearse ya dependiente: la dependencia la "
            "establece la relación entre dos competiciones que existen",
            [
                "créala independiente y después crea la relación con "
                "POST /api/v1/competitions/{superior}/relationships",
                "al crear esa relación, la competición inferior pasa a dependiente sola",
            ],
        )

    # Validar que el contexto se puede construir antes de escribir nada.
    try:
        build_context(tree, ruleset)
    except ValueError as exc:
        raise ValidationFailure(str(exc)) from exc

    competition = m.CompetitionDefinition(
        universe_id=universe.id,
        name=ruleset.name,
        alias=ruleset.alias,
        kind=str(ruleset.kind),
        scope_level=str(ruleset.scope.level),
        country_code=ruleset.scope.country_code,
        # Independiente siempre al nacer; solo una relación lo cambia.
        relationship_mode=str(RelationshipMode.INDEPENDENT),
        territory=list(ruleset.scope.place_keys),
        territory_entity_ids=list(ruleset.scope.entity_ids),
        active=True,
    )
    session.add(competition)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(
            f"ya existe una competición llamada «{ruleset.name}» en este universo"
        ) from exc

    session.add(
        m.CompetitionRuleVersion(
            universe_id=universe.id,
            competition_id=competition.id,
            version=1,
            effective_from=universe.world_date,
            rules_json=ruleset.model_dump(mode="json"),
            schema_version=ruleset.schema_version,
            checksum=ruleset.checksum(),
        )
    )
    record_event(
        session,
        universe,
        SimulationEvent(
            event_type=EventType.COMPETITION_CREATED,
            world_date=universe.world_date,
            entities={"competition": competition.id},
            payload={
                "name": competition.name,
                "kind": competition.kind,
                "scope_level": competition.scope_level,
                "relationship_mode": competition.relationship_mode,
                "club_count": ruleset.generation.club_count,
            },
            headline=f"Se funda {competition.name}, competición independiente",
        ),
    )
    session.commit()
    return competition


def competition_professionalization(session: Session, competition_id: str) -> float:
    """Nivel **efectivo** de la competición, leído de la procedencia guardada.

    No es una etiqueta elegida por nadie: salió de los recursos que sus clubes
    pudieron sostener al generarse (`resolve_effective_level`). Lo usan el motor
    de partidos, para la calidad del juego, y el de movilidad, para reescalar el
    presupuesto de un club que cambia de categoría.
    """
    competition = get_competition(session, competition_id)
    records = session.scalars(
        select(m.GenerationProvenance)
        .where(
            m.GenerationProvenance.universe_id == competition.universe_id,
            m.GenerationProvenance.entity_kind == "competition_context",
        )
        .order_by(m.GenerationProvenance.id)
    ).all()
    for record in records:
        if record.entity_key == competition.name:
            for note in record.notes:
                if note["field"] == "effective_level":
                    return float(note["value"])

    # Si faltara la procedencia, se recalcula el mundo mínimo necesario para
    # obtener el nivel emergente en vez de inventar un número.
    tree = load_place_tree(session, competition.universe_id)
    ruleset = RuleSet.model_validate(current_rule_version(session, competition_id).rules_json)
    universe = get_universe(session, competition.universe_id)
    world = generate_competition_world(
        tree=tree,
        ruleset=ruleset,
        master_seed=ruleset.effective_seed(universe.master_seed),
        edition_key=f"level:{competition.id}",
        world_date=universe.world_date,
        build_calendar=False,
    )
    return world.context.level


def get_competition(session: Session, competition_id: str) -> m.CompetitionDefinition:
    competition = session.get(m.CompetitionDefinition, competition_id)
    if competition is None:
        raise NotFoundError(f"no existe la competición {competition_id}")
    return competition


def current_rule_version(session: Session, competition_id: str) -> m.CompetitionRuleVersion:
    row = session.scalars(
        select(m.CompetitionRuleVersion)
        .where(m.CompetitionRuleVersion.competition_id == competition_id)
        .order_by(m.CompetitionRuleVersion.version.desc())
        .limit(1)
    ).first()
    if row is None:
        raise NotFoundError("la competición no tiene ninguna versión de reglas")
    return row


def generate_edition(
    session: Session, competition_id: str, year: int | None = None
) -> m.CompetitionEdition:
    """Genera el mundo de una edición: clubes, personas, estadios y calendario."""
    competition = get_competition(session, competition_id)
    universe = get_universe(session, competition.universe_id)
    if universe.sim_lock_token is not None:
        raise ConflictError("el universo está simulando; espera a que termine")

    rule_version = current_rule_version(session, competition_id)
    ruleset = RuleSet.model_validate(rule_version.rules_json)
    season_year = year or universe.world_date.year

    existing = session.scalars(
        select(m.CompetitionEdition).where(
            m.CompetitionEdition.competition_id == competition_id,
            m.CompetitionEdition.year == season_year,
        )
    ).first()
    if existing is not None:
        raise ConflictError(
            f"la edición {season_year} de «{competition.name}» ya está generada",
            ["avanza el reloj a la siguiente temporada o consulta la edición existente"],
        )

    tree = load_place_tree(session, competition.universe_id)
    seed = ruleset.effective_seed(universe.master_seed)
    edition = m.CompetitionEdition(
        universe_id=universe.id,
        competition_id=competition.id,
        year=season_year,
        rules_version_id=rule_version.id,
        stage="regular_season",
        status="scheduled",
        seed=seed,
        sim_version=SIM_VERSION,
    )
    session.add(edition)
    session.flush()

    place_ids = _place_ids_of(session, universe.id)

    try:
        world = generate_competition_world(
            tree=tree,
            ruleset=ruleset,
            master_seed=seed,
            edition_key=edition.id,
            world_date=universe.world_date,
        )
    except (RuleValidationError, ScheduleError) as exc:
        session.rollback()
        raise ValidationFailure(exc.message, exc.suggestions) from exc

    # --- Personas -------------------------------------------------------------
    # Ninguna. Generar una competición ya no crea gente: la generación de
    # plantillas se retiró el 25/10/2026 (ADR 0013) y el universo crea sus
    # personas por su cuenta (`person_service.materialize_person`). Un club nace
    # con su identidad, su gobierno, su sede y sus cuentas, y sin jugadores.
    assert not world.people, "generar una competición no crea personas"

    # --- Clubes, estadios e inscripciones -------------------------------------
    entries: list[m.EditionEntry] = []
    club_ids: dict[str, str] = {}
    for club in world.clubs:
        club_row = m.Club(
            universe_id=universe.id,
            club_key=club.key,
            name=club.name,
            short_name=club.short_name,
            nickname=club.nickname,
            home_place_id=place_ids[club.home_place_key],
            institutional_type=str(club.institutional_type),
            foundation_year=club.foundation_year,
            brand=vars(club.brand),
            reputation=vars(club.reputation),
            policies=vars(club.policies),
            fan_base=club.fan_base,
            resource_multiplier=club.resource_multiplier,
            organization=club.organization.as_dict() if club.organization else {},
            finance_profile=club.finances.profile.as_dict() if club.finances.profile else {},
            currency=club.finances.currency,
            annual_budget=club.finances.annual_budget,
            cash=club.finances.cash,
            debt=club.finances.debt,
            history_note=club.history_note,
        )
        session.add(club_row)
        session.flush()
        club_ids[club.key] = club_row.id

        # El organigrama de fundación y las personas que lo encabezan. Lo que
        # nace aquí es lo que el club **necesita** el primer día: su raíz, su
        # dirección y quien lo posee o lo representa. Los demás departamentos
        # aparecerán cuando haya trabajo que los justifique (ADR 0014).
        organization_service.found_chart(
            session,
            universe,
            club_row,
            governance=_governance_of(club),
            season=edition.year,
            place=session.get(m.Place, club_row.home_place_id),
        )

        venue_row = m.Venue(
            universe_id=universe.id,
            venue_key=club.venue.key,
            club_id=club_row.id,
            place_id=place_ids[club.venue.place_key],
            name=club.venue.name,
            venue_type=str(club.venue.venue_type),
            capacity=club.venue.capacity,
            dimensions=venue_dimensions_to_json(club.venue),
            surface=str(club.venue.surface),
            elevation_m=club.venue.elevation_m,
            lat=club.venue.lat,
            lon=club.venue.lon,
            has_roof=club.venue.has_roof,
            maintenance=club.venue.maintenance,
            built_year=club.venue.built_year,
        )
        session.add(venue_row)

        session.add(
            m.ClubMembership(
                universe_id=universe.id,
                club_id=club_row.id,
                competition_id=competition.id,
                membership_kind="member",
                start_edition_id=edition.id,
                start_season=edition.year,
                origin="generated",
            )
        )
        entry = m.EditionEntry(
            universe_id=universe.id,
            edition_id=edition.id,
            participant_kind="club",
            club_id=club_row.id,
            seed_rank=0,
            group_key=world.group_of.get(club.key, ""),
        )
        session.add(entry)
        entries.append(entry)
    session.flush()

    entry_by_club_key = dict(zip([c.key for c in world.clubs], entries, strict=True))
    venue_by_club_id = {
        row.club_id: row
        for row in session.scalars(select(m.Venue).where(m.Venue.universe_id == universe.id)).all()
    }

    # --- Calendario -----------------------------------------------------------
    for game in world.schedule.games:
        home_entry = entry_by_club_key[game.home_key]
        away_entry = entry_by_club_key[game.away_key]
        session.add(
            m.Game(
                universe_id=universe.id,
                edition_id=edition.id,
                stage="regular_season",
                round_index=game.round_index,
                series_key=None,
                game_in_series=game.game_in_series,
                home_entry_id=home_entry.id,
                away_entry_id=away_entry.id,
                home_club_id=home_entry.club_id,
                away_club_id=away_entry.club_id,
                venue_id=venue_by_club_id[home_entry.club_id].id,
                game_date=game.game_date,
                state="scheduled",
            )
        )

    for entry in entries:
        session.add(
            m.Standing(
                universe_id=universe.id,
                edition_id=edition.id,
                entry_id=entry.id,
            )
        )

    store_provenance(session, universe.id, world.records)

    edition.start_date = world.schedule.first_date
    edition.end_date = world.schedule.last_date
    edition.status = "in_progress" if world.schedule.games else "scheduled"
    edition.warnings = world.warnings
    competition.active = True

    for event in world.events:
        event_entities = dict(event.entities)
        event_entities["competition"] = competition.id
        record_event(
            session,
            universe,
            SimulationEvent(
                event_type=event.event_type,
                world_date=event.world_date,
                entities=event_entities,
                payload=event.payload,
                headline=event.headline,
            ),
        )
    session.commit()
    return edition


def store_provenance(session: Session, universe_id: str, records: list[GenerationRecord]) -> None:
    """Guarda la procedencia de lo que un procedimiento generó.

    Pública porque el cierre de temporada también genera números —el
    presupuesto del año siguiente— y tiene que decir de dónde salen.
    """
    for record in records:
        data = record.as_dict()
        session.add(
            m.GenerationProvenance(
                universe_id=universe_id,
                entity_kind=data["entity_kind"],
                entity_key=data["entity_key"][:90],
                procedure=data["procedure"],
                procedure_version=data["procedure_version"],
                seed=data["seed"],
                notes=data["notes"],
                assumptions=data["assumptions"],
            )
        )


def list_competitions(session: Session, universe_id: str) -> list[dict]:
    get_universe(session, universe_id)
    competitions = session.scalars(
        select(m.CompetitionDefinition)
        .where(m.CompetitionDefinition.universe_id == universe_id)
        .order_by(m.CompetitionDefinition.created_at)
    ).all()
    out = []
    for competition in competitions:
        editions = session.scalars(
            select(m.CompetitionEdition)
            .where(m.CompetitionEdition.competition_id == competition.id)
            .order_by(m.CompetitionEdition.year.desc())
        ).all()
        rule_version = session.scalars(
            select(m.CompetitionRuleVersion)
            .where(m.CompetitionRuleVersion.competition_id == competition.id)
            .order_by(m.CompetitionRuleVersion.version.desc())
            .limit(1)
        ).first()
        relationships = session.scalars(
            select(m.CompetitionRelationship).where(
                (m.CompetitionRelationship.source_id == competition.id)
                | (m.CompetitionRelationship.target_id == competition.id)
            )
        ).all()
        paths = session.scalars(
            select(m.QualificationPath).where(
                (m.QualificationPath.source_competition_id == competition.id)
                | (m.QualificationPath.target_competition_id == competition.id)
            )
        ).all()
        out.append(
            {
                "id": competition.id,
                "name": competition.name,
                "alias": competition.alias,
                "kind": competition.kind,
                "scope_level": competition.scope_level,
                "country_code": competition.country_code,
                "relationship_mode": competition.relationship_mode,
                "territory": competition.territory,
                "active": competition.active,
                "club_count": (
                    rule_version.rules_json["generation"]["club_count"] if rule_version else 0
                ),
                # El tablero de dependencias toma estas columnas del reglamento
                # congelado; no inventa una estructura genérica para una liga
                # ya creada.
                "education_track": (
                    (rule_version.rules_json.get("education") or {}).get("track")
                    if rule_version
                    else None
                ),
                "structure": _structure_summary(rule_version.rules_json if rule_version else {}),
                "hierarchy_links": len(relationships),
                "qualification_paths": len(paths),
                "editions": [
                    {
                        "id": edition.id,
                        "year": edition.year,
                        "stage": edition.stage,
                        "status": edition.status,
                        "start_date": edition.start_date,
                        "end_date": edition.end_date,
                        "warnings": edition.warnings,
                    }
                    for edition in editions
                ],
            }
        )
    return out


def _structure_summary(rules_json: dict) -> list[dict[str, int | str]]:
    """Divisiones de la primera fase para representarlas en el lienzo visual."""
    structure = rules_json.get("structure") or {}
    stages = structure.get("stages") or []
    if stages:
        divisions = stages[0].get("divisions") or []
        return [
            {
                "key": str(item.get("key", index)),
                "label": str(item.get("label", "Tabla")),
                "slots": int(item.get("slots", 0)),
            }
            for index, item in enumerate(divisions)
        ]
    groups = structure.get("groups") or []
    if groups:
        return [
            {
                "key": str(index),
                "label": str(item.get("label", "Grupo")),
                "slots": int(item.get("slots", 0)),
            }
            for index, item in enumerate(groups)
        ]
    count = int((rules_json.get("generation") or {}).get("club_count", 0))
    return [{"key": "general", "label": "Tabla general", "slots": count}] if count else []


def next_season_year(session: Session, competition_id: str) -> int:
    latest = session.scalar(
        select(func.max(m.CompetitionEdition.year)).where(
            m.CompetitionEdition.competition_id == competition_id
        )
    )
    return (latest or date.today().year) + 1
