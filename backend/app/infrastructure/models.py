"""Modelos de persistencia.

Reglas que el esquema hace cumplir:

- Toda entidad del mundo lleva `universe_id`. Nada cruza universos.
- `competition_editions` apunta a una versión **congelada** de reglas.
- Las entradas en una edición (`edition_entries`) son distintas del club.
- `simulation_commands.idempotency_key` es única: repetir un avance con la misma
  clave no puede duplicar partidos.
- Las entradas lanzadas se guardan en outs enteros (`outs_recorded`).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base, JSONType, MoneyType, new_id


def _now() -> datetime:
    return datetime.now(UTC)


class Universe(Base):
    __tablename__ = "universes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    world_date: Mapped[date] = mapped_column(Date, nullable=False)
    master_seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sim_version: Mapped[str] = mapped_column(String(32), nullable=False)
    fixture_version: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    #: Moneda **opcional** de presentación. La moneda real de cada institución
    #: sale de su jurisdicción (ancla monetaria del territorio), no de aquí: el
    #: universo no presume la moneda del idioma de la interfaz.
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    config: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    #: Lock por universo: impide dos avances simultáneos sobre el mismo mundo.
    sim_lock_token: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sim_lock_acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        UniqueConstraint("name", name="uq_universes_name"),
        CheckConstraint("master_seed >= 0", name="ck_universes_seed_non_negative"),
    )


class GazetteerCountry(Base):
    """Países y territorios del gazetteer mundial. Datos de referencia, no de un universo.

    `currency_code` es la autoridad de «¿en qué moneda opera una institución de
    este territorio?» y viene de `countryInfo.txt` de GeoNames, que publica el
    código ISO 4217 de cada jurisdicción. El `reference_monthly_cost` —lo que
    convierte índices en importes— **solo existe donde está curado**: sin él, las
    cuentas de los clubes de ese país quedan sin cuantificar en vez de
    inventarse.
    """

    __tablename__ = "gazetteer_countries"

    iso2: Mapped[str] = mapped_column(String(2), primary_key=True)
    iso3: Mapped[str] = mapped_column(String(3), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    capital: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    continent: Mapped[str] = mapped_column(String(2), nullable=False, default="")
    currency_code: Mapped[str | None] = mapped_column(String(3))
    currency_name: Mapped[str | None] = mapped_column(String(60))
    population: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    area_km2: Mapped[float | None] = mapped_column(Float)
    geoname_id: Mapped[int | None] = mapped_column(BigInteger)
    languages: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    #: Coste mensual de referencia de un hogar, en moneda local. Curado.
    reference_monthly_cost: Mapped[Decimal | None] = mapped_column(MoneyType)
    reference_cost_year: Mapped[int | None] = mapped_column(Integer)
    reference_cost_sources: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="geonames")
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class GazetteerEntity(Base):
    """Una entidad geográfica del mundo real, con identificador estable.

    `source` + `source_id` es la referencia externa —para GeoNames, el
    `geonameid`—, de modo que reimportar no duplica y cualquier lugar se puede
    rastrear hasta su fuente. `id` es nuestra clave propia y es la que guardan
    las competiciones: si mañana se cambia de proveedor, las competiciones no se
    rompen.

    `resolution_status` recorre los estados que pide el FIX V2 §4.5:
    `verified` cuando la entidad viene resuelta de la fuente con jerarquía, e
    `incomplete` cuando falta algo relevante —por ejemplo su división
    administrativa— y hay que decirlo en vez de disimularlo.
    """

    __tablename__ = "gazetteer_entities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="geonames")
    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    ascii_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    #: Nombre y variantes, en minúsculas y sin acentos. Es el índice de búsqueda:
    #: permite encontrar «Mexico City» escribiendo «Ciudad de México».
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: Variantes legibles, para mostrarlas al desambiguar.
    variants: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    country_iso2: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    admin1_code: Mapped[str | None] = mapped_column(String(24))
    admin2_code: Mapped[str | None] = mapped_column(String(48))
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("gazetteer_entities.id", ondelete="SET NULL")
    )
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    elevation_m: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    population: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    feature_class: Mapped[str] = mapped_column(String(4), nullable=False, default="")
    feature_code: Mapped[str] = mapped_column(String(12), nullable=False, default="")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    #: verified | incomplete
    resolution_status: Mapped[str] = mapped_column(String(16), nullable=False, default="verified")
    #: Qué falta, cuando el estado es `incomplete`.
    resolution_notes: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_gazetteer_source_id"),
        Index("ix_gazetteer_search", "search_text"),
        Index("ix_gazetteer_country_kind", "country_iso2", "kind"),
    )


class GazetteerBoundary(Base):
    """Límite administrativo de una entidad, cuando la fuente lo publica.

    No hay polígonos inventados: si geoBoundaries no publica el límite de una
    jurisdicción, no hay fila aquí, y la competición tiene que delimitarse de
    otra forma —radio desde el centroide o lista explícita de territorios—, que
    es lo que el FIX V2 §4.5 pide decir en voz alta en vez de dibujar fronteras
    aproximadas como si fueran reales.
    """

    __tablename__ = "gazetteer_boundaries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    entity_id: Mapped[str] = mapped_column(
        ForeignKey("gazetteer_entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="geoboundaries")
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    admin_level: Mapped[str] = mapped_column(String(8), nullable=False, default="ADM1")
    #: GeoJSON simplificado. El CRS es WGS 84 (EPSG:4326), como publica la fuente.
    geometry: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    crs: Mapped[str] = mapped_column(String(16), nullable=False, default="EPSG:4326")
    licence: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    licence_source: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    represented_year: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    downloaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        UniqueConstraint("entity_id", "source", "admin_level", name="uq_boundary_entity_level"),
    )


class Place(Base):
    __tablename__ = "places"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    place_key: Mapped[str] = mapped_column(String(48), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("places.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    country_code: Mapped[str] = mapped_column(String(3), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    elevation_m: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: observed | estimated | fictional — la interfaz lo muestra tal cual.
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    sources: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    #: Ancla monetaria de la jurisdicción (solo en países): moneda de curso
    #: legal y coste mensual de referencia, con su año y su confianza. Es el
    #: único punto donde los índices relativos se convierten en importes.
    economy: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    #: Entidad del gazetteer mundial de la que salió este lugar, si vino de ahí
    #: y no del fixture curado. Es la referencia estable a la fuente.
    gazetteer_entity_id: Mapped[str | None] = mapped_column(
        ForeignKey("gazetteer_entities.id", ondelete="SET NULL")
    )

    __table_args__ = (UniqueConstraint("universe_id", "place_key", name="uq_places_universe_key"),)


class RegionProfile(Base):
    __tablename__ = "region_profiles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    place_id: Mapped[str] = mapped_column(
        ForeignKey("places.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ref_year: Mapped[int] = mapped_column(Integer, nullable=False)
    population: Mapped[int] = mapped_column(BigInteger, nullable=False)
    economy_index: Mapped[float] = mapped_column(Float, nullable=False)
    baseball_culture_index: Mapped[float] = mapped_column(Float, nullable=False)
    cost_of_living_index: Mapped[float] = mapped_column(Float, nullable=False)
    infrastructure_index: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    sources: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)

    __table_args__ = (
        UniqueConstraint("place_id", "ref_year", name="uq_region_profile_place_year"),
    )


class CompetitionDraft(Base):
    """Borrador de una competición, con su estado y su historial de ediciones.

    Existe para que el asistente pueda guardar lo que el usuario va escribiendo
    sin crear nada en el mundo, y para que la confirmación pueda comprobar que
    lo que se confirma es lo que se previsualizó.

    El estado recorre el ciclo del FIX V2 §12.1:

    ```text
    draft → geography_pending → geography_resolved → context_ready
          → preview_ready | preview_warning | preview_blocked → committed
    ```

    `intent_fingerprint` es el SHA-256 de la intención canónica. Si el usuario
    cambia una regla o el territorio, la huella cambia y la previsualización
    anterior queda obsoleta: confirmarla devuelve conflicto en vez de crear un
    mundo que nadie vio.
    """

    __tablename__ = "competition_drafts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    #: La intención del usuario tal cual, sin resolver.
    intent: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    intent_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    #: Última previsualización calculada para esta huella.
    preview_id: Mapped[str | None] = mapped_column(String(32))
    #: Competición creada al confirmar, si ya se confirmó.
    competition_id: Mapped[str | None] = mapped_column(
        ForeignKey("competition_definitions.id", ondelete="SET NULL")
    )
    issues: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class GenerationPreview(Base):
    """Una propuesta del generador, **inmutable** y con su huella.

    Previsualizar no escribe en el mundo: lo que se guarda aquí es la propuesta
    —los clubes candidatos con sus cuentas, el contexto y los problemas
    detectados—, no entidades del universo. Al confirmar se vuelve a generar con
    la misma semilla y la misma intención, así que el resultado es el mismo.

    Por qué los candidatos y los problemas van en columnas JSON en vez de en
    tablas aparte, como sugería el documento: la propuesta es inmutable y
    siempre se lee entera. Normalizarla no permitiría consultar nada que importe
    y multiplicaría las filas por el número de clubes.
    """

    __tablename__ = "generation_previews"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    draft_id: Mapped[str | None] = mapped_column(
        ForeignKey("competition_drafts.id", ondelete="CASCADE"), index=True
    )
    #: SHA-256 de la intención canónica que produjo esta propuesta.
    intent_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    ruleset_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Semilla efectiva: con la misma, la propuesta se reproduce.
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: preview_ready | preview_warning | preview_blocked
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="preview_ready")
    context: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    candidates: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    issues: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    #: Competición creada a partir de esta propuesta, si se confirmó.
    committed_competition_id: Mapped[str | None] = mapped_column(
        ForeignKey("competition_definitions.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (Index("ix_preview_fingerprint", "universe_id", "intent_fingerprint"),)


class CompetitionDefinition(Base):
    __tablename__ = "competition_definitions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    alias: Mapped[str | None] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    scope_level: Mapped[str] = mapped_column(String(20), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(3))
    #: `independent` por omisión. Solo cambia si el usuario crea el vínculo.
    relationship_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="independent"
    )
    territory: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    #: Entidades del gazetteer mundial que el usuario resolvió, si el territorio
    #: vino de ahí. Es la referencia estable: `territory` guarda las claves ya
    #: materializadas en este universo.
    territory_entity_ids: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    rule_versions: Mapped[list[CompetitionRuleVersion]] = relationship(
        back_populates="competition", cascade="all, delete-orphan"
    )
    editions: Mapped[list[CompetitionEdition]] = relationship(
        back_populates="competition", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("universe_id", "name", name="uq_competition_universe_name"),)


class CompetitionRuleVersion(Base):
    __tablename__ = "competition_rule_versions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competition_id: Mapped[str] = mapped_column(
        ForeignKey("competition_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    rules_json: Mapped[dict] = mapped_column(JSONType, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    competition: Mapped[CompetitionDefinition] = relationship(back_populates="rule_versions")

    __table_args__ = (
        UniqueConstraint("competition_id", "version", name="uq_rule_version_competition"),
    )


class CompetitionEdition(Base):
    __tablename__ = "competition_editions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competition_id: Mapped[str] = mapped_column(
        ForeignKey("competition_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    rules_version_id: Mapped[str] = mapped_column(
        ForeignKey("competition_rule_versions.id", ondelete="RESTRICT"), nullable=False
    )
    #: regular_season | playoffs | completed
    stage: Mapped[str] = mapped_column(String(24), nullable=False, default="regular_season")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="scheduled")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sim_version: Mapped[str] = mapped_column(String(32), nullable=False)
    champion_club_id: Mapped[str | None] = mapped_column(
        ForeignKey("clubs.id", ondelete="SET NULL")
    )
    warnings: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    #: Clasificados con pase directo que esperan la segunda ronda, cuando las
    #: plazas de playoff no son potencia de dos. Se vacía en cuanto entran.
    playoff_byes: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    #: Posición de la fase en curso dentro de la secuencia del reglamento. El
    #: nombre de la fase está en `stage`; esto dice **cuál** de las declaradas
    #: es, que es lo que hace falta para saber qué viene después.
    stage_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    competition: Mapped[CompetitionDefinition] = relationship(back_populates="editions")

    __table_args__ = (
        UniqueConstraint("competition_id", "year", name="uq_edition_competition_year"),
    )


class Club(Base):
    __tablename__ = "clubs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    club_key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    short_name: Mapped[str] = mapped_column(String(60), nullable=False)
    nickname: Mapped[str] = mapped_column(String(60), nullable=False)
    home_place_id: Mapped[str] = mapped_column(
        ForeignKey("places.id", ondelete="RESTRICT"), nullable=False
    )
    institutional_type: Mapped[str] = mapped_column(String(24), nullable=False)
    foundation_year: Mapped[int] = mapped_column(Integer, nullable=False)
    brand: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    reputation: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    policies: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    fan_base: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resource_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    #: Organización que el club se dio: gobierno, acuerdo de sede y reparto de
    #: responsabilidades. Es un resultado del generador, nunca una entrada.
    organization: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    #: Desglose de las cuentas con el origen y la base de cada importe.
    finance_profile: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    #: Moneda de la jurisdicción del club. `None` si su territorio no tiene
    #: ancla monetaria declarada: entonces sus importes quedan sin determinar.
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    annual_budget: Mapped[Decimal] = mapped_column(MoneyType, nullable=False, default=0)
    cash: Mapped[Decimal] = mapped_column(MoneyType, nullable=False, default=0)
    debt: Mapped[Decimal] = mapped_column(MoneyType, nullable=False, default=0)
    history_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: active | folded. Un club que desaparece conserva su fila y su historia:
    #: no se borra, deja de competir.
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    #: Temporadas consecutivas sin poder cubrir sus obligaciones. Una mala no
    #: cierra un club; una racha sí.
    seasons_insolvent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("universe_id", "club_key", name="uq_clubs_universe_key"),)


class ClubMembership(Base):
    """Participación de un club en una competición.

    Ascender o descender cambia filas de aquí, nunca el `club.id`. La vigencia
    se expresa en temporadas (`start_season`/`end_season`) y no solo en
    ediciones, porque un ascenso se resuelve cuando la edición de destino
    todavía no existe: el club ya es miembro de su nueva competición desde la
    temporada siguiente, aunque su calendario se construya después.
    """

    __tablename__ = "club_memberships"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    club_id: Mapped[str] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competition_id: Mapped[str] = mapped_column(
        ForeignKey("competition_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    membership_kind: Mapped[str] = mapped_column(String(24), nullable=False, default="member")
    start_edition_id: Mapped[str | None] = mapped_column(
        ForeignKey("competition_editions.id", ondelete="SET NULL")
    )
    end_edition_id: Mapped[str | None] = mapped_column(
        ForeignKey("competition_editions.id", ondelete="SET NULL")
    )
    #: Primera temporada en la que la pertenencia es válida.
    start_season: Mapped[int | None] = mapped_column(Integer)
    #: Última temporada en la que fue válida. NULL = sigue vigente.
    end_season: Mapped[int | None] = mapped_column(Integer)
    #: Cómo entró el club: generación inicial, ascenso o descenso.
    origin: Mapped[str] = mapped_column(String(24), nullable=False, default="generated")

    __table_args__ = (
        Index("ix_membership_competition_season", "competition_id", "start_season", "end_season"),
    )


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    venue_key: Mapped[str] = mapped_column(String(90), nullable=False)
    club_id: Mapped[str | None] = mapped_column(ForeignKey("clubs.id", ondelete="SET NULL"))
    place_id: Mapped[str] = mapped_column(
        ForeignKey("places.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    venue_type: Mapped[str] = mapped_column(String(32), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    dimensions: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    surface: Mapped[str] = mapped_column(String(24), nullable=False)
    elevation_m: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    has_roof: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    maintenance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    built_year: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint("universe_id", "venue_key", name="uq_venues_universe_key"),)


class Person(Base):
    __tablename__ = "people"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_key: Mapped[str] = mapped_column(String(90), nullable=False)
    given_name: Mapped[str] = mapped_column(String(80), nullable=False)
    surnames: Mapped[str] = mapped_column(String(120), nullable=False)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    origin_place_id: Mapped[str] = mapped_column(
        ForeignKey("places.id", ondelete="RESTRICT"), nullable=False
    )
    nationalities: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    role: Mapped[str] = mapped_column(String(24), nullable=False, default="player")
    primary_position: Mapped[str] = mapped_column(String(4), nullable=False)
    secondary_positions: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    pitcher_role: Mapped[str | None] = mapped_column(String(4))
    bats: Mapped[str] = mapped_column(String(1), nullable=False)
    throws: Mapped[str] = mapped_column(String(1), nullable=False)
    height_cm: Mapped[int] = mapped_column(Integer, nullable=False)
    weight_kg: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Bloques de atributos. El potencial real vive aquí; lo que los scouts
    #: creen se guarda aparte en `development.scouted_potential`.
    attributes: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    overall: Mapped[float] = mapped_column(Float, nullable=False)
    state: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")

    __table_args__ = (
        UniqueConstraint("universe_id", "person_key", name="uq_people_universe_key"),
        Index("ix_people_universe_overall", "universe_id", "overall"),
    )


class RosterAssignment(Base):
    __tablename__ = "roster_assignments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    club_id: Mapped[str] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")

    __table_args__ = (Index("ix_roster_active", "universe_id", "person_id", "status"),)


class EditionEntry(Base):
    """Inscripción de un participante en una edición concreta."""

    __tablename__ = "edition_entries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    edition_id: Mapped[str] = mapped_column(
        ForeignKey("competition_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    participant_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="club")
    club_id: Mapped[str | None] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"))
    seed_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    #: Grupo, división o conferencia en la que juega esta temporada. Vacío si la
    #: competición es de tabla única. Se guarda por edición y no por club,
    #: porque el reparto se rehace cada temporada: un club ascendido cambia de
    #: división sin cambiar de identidad.
    group_key: Mapped[str] = mapped_column(String(40), nullable=False, default="")

    __table_args__ = (UniqueConstraint("edition_id", "club_id", name="uq_entry_edition_club"),)


class Game(Base):
    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    edition_id: Mapped[str] = mapped_column(
        ForeignKey("competition_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(24), nullable=False, default="regular_season")
    round_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    series_key: Mapped[str | None] = mapped_column(String(24))
    game_in_series: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    home_entry_id: Mapped[str] = mapped_column(
        ForeignKey("edition_entries.id", ondelete="CASCADE"), nullable=False
    )
    away_entry_id: Mapped[str] = mapped_column(
        ForeignKey("edition_entries.id", ondelete="CASCADE"), nullable=False
    )
    home_club_id: Mapped[str] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"))
    away_club_id: Mapped[str] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"))
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id", ondelete="RESTRICT"))
    game_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled")
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    innings_played: Mapped[int | None] = mapped_column(Integer)
    line_score: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    weather: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    park_note: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    engine_version: Mapped[str | None] = mapped_column(String(40))
    seed: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (
        Index("ix_games_edition_date", "edition_id", "game_date"),
        Index("ix_games_universe_state_date", "universe_id", "state", "game_date"),
    )


class GameEvent(Base):
    __tablename__ = "game_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    game_id: Mapped[str] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    __table_args__ = (UniqueConstraint("game_id", "seq", name="uq_game_event_seq"),)


class PlayerGameStats(Base):
    __tablename__ = "player_game_stats"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    game_id: Mapped[str] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    edition_id: Mapped[str] = mapped_column(
        ForeignKey("competition_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), nullable=False, index=True
    )
    club_id: Mapped[str] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    lineup_slot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    position: Mapped[str] = mapped_column(String(4), nullable=False, default="DH")
    plate_appearances: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    at_bats: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    singles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    doubles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    triples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    home_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runs_batted_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    walks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hit_by_pitch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    strikeouts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sac_flies: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stolen_bases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    caught_stealing: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reached_on_error: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    putouts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assists: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("game_id", "person_id", name="uq_player_stats_game_person"),
        Index("ix_player_stats_edition_person", "edition_id", "person_id"),
    )


class PitcherGameStats(Base):
    __tablename__ = "pitcher_game_stats"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    game_id: Mapped[str] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    edition_id: Mapped[str] = mapped_column(
        ForeignKey("competition_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), nullable=False, index=True
    )
    club_id: Mapped[str] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    is_starter: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Entradas lanzadas en OUTS ENTEROS. Nunca flotante.
    outs_recorded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    batters_faced: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pitches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hits_allowed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runs_allowed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    earned_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    walks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hit_batsmen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    strikeouts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    home_runs_allowed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    win: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    loss: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    save: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("game_id", "person_id", name="uq_pitcher_stats_game_person"),
        CheckConstraint("earned_runs <= runs_allowed", name="ck_pitcher_er_le_r"),
        Index("ix_pitcher_stats_edition_person", "edition_id", "person_id"),
    )


class TeamGameStats(Base):
    __tablename__ = "team_game_stats"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    game_id: Mapped[str] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    club_id: Mapped[str] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False)
    runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    left_on_base: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    outs_suffered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("game_id", "club_id", name="uq_team_stats_game_club"),)


class Standing(Base):
    __tablename__ = "standings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    edition_id: Mapped[str] = mapped_column(
        ForeignKey("competition_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_id: Mapped[str] = mapped_column(
        ForeignKey("edition_entries.id", ondelete="CASCADE"), nullable=False
    )
    wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ties: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runs_for: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runs_against: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    home_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    home_losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    away_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    away_losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Puesto dentro de su grupo. 0 cuando la competición es de tabla única.
    group_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Fase a la que pertenece esta fila. Una liguilla entre clasificados tiene
    #: su propia tabla: empieza de cero y no arrastra los partidos de la fase
    #: anterior.
    stage_key: Mapped[str] = mapped_column(String(40), nullable=False, default="regular_season")
    streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_ten: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tiebreak_note: Mapped[str] = mapped_column(String(80), nullable=False, default="")

    __table_args__ = (
        UniqueConstraint(
            "edition_id", "entry_id", "stage_key", name="uq_standing_edition_entry_stage"
        ),
    )


class PlayoffSeriesRow(Base):
    __tablename__ = "playoff_series"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    edition_id: Mapped[str] = mapped_column(
        ForeignKey("competition_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    series_key: Mapped[str] = mapped_column(String(24), nullable=False)
    round_index: Mapped[int] = mapped_column(Integer, nullable=False)
    high_seed_club_id: Mapped[str] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"))
    low_seed_club_id: Mapped[str] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"))
    best_of: Mapped[int] = mapped_column(Integer, nullable=False)
    high_seed_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    low_seed_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    winner_club_id: Mapped[str | None] = mapped_column(ForeignKey("clubs.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")

    __table_args__ = (UniqueConstraint("edition_id", "series_key", name="uq_series_edition_key"),)


class CompetitionRelationship(Base):
    """Relación explícita entre competiciones. **Autoridad única.**

    La configuración efectiva (plazas de intercambio, criterios de cada extremo,
    temporada de entrada en vigor) vive aquí y en ningún otro sitio, para que
    las dos competiciones muestren la misma regla.

    El intercambio de clubes al cerrar temporada lee esta fila y solo esta
    fila; ver `app.application.mobility_service`.
    """

    __tablename__ = "competition_relationships"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: En una relación de ascenso/descenso, `source` es la superior.
    source_id: Mapped[str] = mapped_column(
        ForeignKey("competition_definitions.id", ondelete="CASCADE"), nullable=False
    )
    target_id: Mapped[str] = mapped_column(
        ForeignKey("competition_definitions.id", ondelete="CASCADE"), nullable=False
    )
    relation_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    effective_from_season: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        UniqueConstraint(
            "source_id", "target_id", "relation_kind", name="uq_relationship_pair_kind"
        ),
        CheckConstraint("source_id <> target_id", name="ck_relationship_not_self"),
    )


class QualificationPath(Base):
    """Ruta de cupos hacia otra competición. **No** crea jerarquía."""

    __tablename__ = "qualification_paths"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_competition_id: Mapped[str] = mapped_column(
        ForeignKey("competition_definitions.id", ondelete="CASCADE"), nullable=False
    )
    target_competition_id: Mapped[str] = mapped_column(
        ForeignKey("competition_definitions.id", ondelete="CASCADE"), nullable=False
    )
    slot_rule: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint(
            "source_competition_id <> target_competition_id", name="ck_qualification_not_self"
        ),
    )


class ClubSeasonLedger(Base):
    """Liquidación de una temporada para un club: lo cobrado y lo pagado.

    Es el libro contable que pide el FIX V2 §7.1, y la diferencia con el
    presupuesto importa: aquí está lo que **ocurrió**. Un patrocinio prometido
    que no se cobró figura con su importe esperado y su cobro real, y un partido
    que no se jugó no vendió entradas.

    La clave única `(club_id, season)` impide liquidar dos veces la misma
    temporada cuando se reintenta un avance.
    """

    __tablename__ = "club_season_ledgers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    club_id: Mapped[str] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competition_id: Mapped[str | None] = mapped_column(
        ForeignKey("competition_definitions.id", ondelete="SET NULL")
    )
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str | None] = mapped_column(String(8))
    collected: Mapped[Decimal] = mapped_column(MoneyType, nullable=False, default=0)
    paid: Mapped[Decimal] = mapped_column(MoneyType, nullable=False, default=0)
    result: Mapped[Decimal] = mapped_column(MoneyType, nullable=False, default=0)
    cash_start: Mapped[Decimal] = mapped_column(MoneyType, nullable=False, default=0)
    cash_end: Mapped[Decimal] = mapped_column(MoneyType, nullable=False, default=0)
    debt_start: Mapped[Decimal] = mapped_column(MoneyType, nullable=False, default=0)
    debt_end: Mapped[Decimal] = mapped_column(MoneyType, nullable=False, default=0)
    #: healthy | strained | insolvent
    outcome: Mapped[str] = mapped_column(String(16), nullable=False, default="healthy")
    #: Asientos con su causa: cada línea dice qué se esperaba y qué entró.
    entries: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    notes: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        UniqueConstraint("club_id", "season", name="uq_ledger_club_season"),
        Index("ix_ledger_universe_season", "universe_id", "season"),
    )


class ClubOrganizationChange(Base):
    """Un cambio en la organización de un club, con su causa y su fecha.

    Es la historia institucional que el FIX V2 §11.2 pide conservar: la forma de
    gobierno de un club, su sede y su base social cambian con los años, y el
    registro dice **por qué** cambió cada cosa. No se sobrescribe el pasado.
    """

    __tablename__ = "club_organization_changes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    club_id: Mapped[str] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    field: Mapped[str] = mapped_column(String(40), nullable=False)
    before: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    after: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SeasonTransition(Base):
    """Un cierre de temporada ya resuelto entre competiciones vinculadas.

    Es el registro que hace idempotente el intercambio: la clave única
    (competición superior, temporada) impide que un reintento del avance mueva
    dos veces a los mismos clubes. Guarda el plan completo, con sus motivos, para
    que el historial pueda explicar cada movimiento.
    """

    __tablename__ = "season_transitions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: La competición superior de la relación; ella es la autoridad de la cuota.
    upper_competition_id: Mapped[str] = mapped_column(
        ForeignKey("competition_definitions.id", ondelete="CASCADE"), nullable=False
    )
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_on: Mapped[date] = mapped_column(Date, nullable=False)
    #: Plan tal como lo devolvió el motor: movimientos, rechazos y notas.
    plan: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    promotions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    relegations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        UniqueConstraint("upper_competition_id", "season", name="uq_transition_competition_season"),
    )


class SimulationEventRow(Base):
    __tablename__ = "simulation_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    world_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entities: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    headline: Mapped[str | None] = mapped_column(String(240))
    causation_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (Index("ix_sim_events_universe_date", "universe_id", "world_date"),)


class SimulationCommand(Base):
    """Comando recibido. `idempotency_key` única: reintentar no duplica."""

    __tablename__ = "simulation_commands"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    command_type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="accepted")
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    job_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        UniqueConstraint("universe_id", "idempotency_key", name="uq_command_idempotency"),
    )


class SimJob(Base):
    __tablename__ = "sim_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    command_type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    progress: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GenerationProvenance(Base):
    """De dónde salió cada cosa generada: procedimiento, semilla y supuestos."""

    __tablename__ = "generation_provenance"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    universe_id: Mapped[str] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_key: Mapped[str] = mapped_column(String(90), nullable=False)
    procedure: Mapped[str] = mapped_column(String(60), nullable=False)
    procedure_version: Mapped[str] = mapped_column(String(32), nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    notes: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    assumptions: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)

    __table_args__ = (
        Index("ix_provenance_universe_entity", "universe_id", "entity_kind", "entity_key"),
    )
