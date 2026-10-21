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
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="MXN")
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
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="MXN")
    annual_budget: Mapped[Decimal] = mapped_column(MoneyType, nullable=False, default=0)
    cash: Mapped[Decimal] = mapped_column(MoneyType, nullable=False, default=0)
    debt: Mapped[Decimal] = mapped_column(MoneyType, nullable=False, default=0)
    history_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")

    __table_args__ = (UniqueConstraint("universe_id", "club_key", name="uq_clubs_universe_key"),)


class ClubMembership(Base):
    """Participación de un club en una competición.

    Ascender o descender cambia filas de aquí, nunca el `club.id`.
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
    streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_ten: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tiebreak_note: Mapped[str] = mapped_column(String(80), nullable=False, default="")

    __table_args__ = (UniqueConstraint("edition_id", "entry_id", name="uq_standing_edition_entry"),)


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

    Etapa 2: las validaciones están activas; el intercambio de clubes al cerrar
    temporada todavía no está implementado.
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
