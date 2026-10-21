"""esquema inicial

Revision ID: 1df364013388
Revises: 
Create Date: 2026-10-20 19:47:21.441005
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision = '1df364013388'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('universes',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('world_date', sa.Date(), nullable=False),
    sa.Column('master_seed', sa.BigInteger(), nullable=False),
    sa.Column('sim_version', sa.String(length=32), nullable=False),
    sa.Column('fixture_version', sa.String(length=32), nullable=False),
    sa.Column('currency', sa.String(length=8), nullable=False),
    sa.Column('config', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('sim_lock_token', sa.String(length=32), nullable=True),
    sa.Column('sim_lock_acquired_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('master_seed >= 0', name='ck_universes_seed_non_negative'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name', name='uq_universes_name')
    )
    op.create_table('competition_definitions',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('alias', sa.String(length=32), nullable=True),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('scope_level', sa.String(length=20), nullable=False),
    sa.Column('country_code', sa.String(length=3), nullable=True),
    sa.Column('relationship_mode', sa.String(length=16), nullable=False),
    sa.Column('territory', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('universe_id', 'name', name='uq_competition_universe_name')
    )
    with op.batch_alter_table('competition_definitions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_competition_definitions_universe_id'), ['universe_id'], unique=False)

    op.create_table('generation_provenance',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('entity_kind', sa.String(length=40), nullable=False),
    sa.Column('entity_key', sa.String(length=90), nullable=False),
    sa.Column('procedure', sa.String(length=60), nullable=False),
    sa.Column('procedure_version', sa.String(length=32), nullable=False),
    sa.Column('seed', sa.BigInteger(), nullable=False),
    sa.Column('notes', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('assumptions', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('generation_provenance', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_generation_provenance_universe_id'), ['universe_id'], unique=False)
        batch_op.create_index('ix_provenance_universe_entity', ['universe_id', 'entity_kind', 'entity_key'], unique=False)

    op.create_table('places',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('place_key', sa.String(length=48), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('parent_id', sa.String(length=32), nullable=True),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('country_code', sa.String(length=3), nullable=False),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('lat', sa.Float(), nullable=False),
    sa.Column('lon', sa.Float(), nullable=False),
    sa.Column('elevation_m', sa.Integer(), nullable=False),
    sa.Column('confidence', sa.String(length=20), nullable=False),
    sa.Column('sources', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.ForeignKeyConstraint(['parent_id'], ['places.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('universe_id', 'place_key', name='uq_places_universe_key')
    )
    with op.batch_alter_table('places', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_places_universe_id'), ['universe_id'], unique=False)

    op.create_table('sim_jobs',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('command_type', sa.String(length=40), nullable=False),
    sa.Column('payload', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('progress', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('sim_jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sim_jobs_universe_id'), ['universe_id'], unique=False)

    op.create_table('simulation_commands',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('command_type', sa.String(length=40), nullable=False),
    sa.Column('payload', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('idempotency_key', sa.String(length=80), nullable=False),
    sa.Column('job_id', sa.String(length=32), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('universe_id', 'idempotency_key', name='uq_command_idempotency')
    )
    with op.batch_alter_table('simulation_commands', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_simulation_commands_universe_id'), ['universe_id'], unique=False)

    op.create_table('simulation_events',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('world_date', sa.Date(), nullable=False),
    sa.Column('event_type', sa.String(length=40), nullable=False),
    sa.Column('entities', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('payload', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('headline', sa.String(length=240), nullable=True),
    sa.Column('causation_id', sa.String(length=32), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('simulation_events', schema=None) as batch_op:
        batch_op.create_index('ix_sim_events_universe_date', ['universe_id', 'world_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_simulation_events_universe_id'), ['universe_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_simulation_events_world_date'), ['world_date'], unique=False)

    op.create_table('clubs',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('club_key', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=140), nullable=False),
    sa.Column('short_name', sa.String(length=60), nullable=False),
    sa.Column('nickname', sa.String(length=60), nullable=False),
    sa.Column('home_place_id', sa.String(length=32), nullable=False),
    sa.Column('institutional_type', sa.String(length=24), nullable=False),
    sa.Column('foundation_year', sa.Integer(), nullable=False),
    sa.Column('brand', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('reputation', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('policies', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('fan_base', sa.Integer(), nullable=False),
    sa.Column('resource_multiplier', sa.Float(), nullable=False),
    sa.Column('currency', sa.String(length=8), nullable=False),
    sa.Column('annual_budget', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('cash', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('debt', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('history_note', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.ForeignKeyConstraint(['home_place_id'], ['places.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('universe_id', 'club_key', name='uq_clubs_universe_key')
    )
    with op.batch_alter_table('clubs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_clubs_universe_id'), ['universe_id'], unique=False)

    op.create_table('competition_relationships',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('source_id', sa.String(length=32), nullable=False),
    sa.Column('target_id', sa.String(length=32), nullable=False),
    sa.Column('relation_kind', sa.String(length=32), nullable=False),
    sa.Column('config', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('effective_from_season', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('source_id <> target_id', name='ck_relationship_not_self'),
    sa.ForeignKeyConstraint(['source_id'], ['competition_definitions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['target_id'], ['competition_definitions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_id', 'target_id', 'relation_kind', name='uq_relationship_pair_kind')
    )
    with op.batch_alter_table('competition_relationships', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_competition_relationships_universe_id'), ['universe_id'], unique=False)

    op.create_table('competition_rule_versions',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('competition_id', sa.String(length=32), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('rules_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('schema_version', sa.String(length=16), nullable=False),
    sa.Column('checksum', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['competition_id'], ['competition_definitions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('competition_id', 'version', name='uq_rule_version_competition')
    )
    with op.batch_alter_table('competition_rule_versions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_competition_rule_versions_competition_id'), ['competition_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_competition_rule_versions_universe_id'), ['universe_id'], unique=False)

    op.create_table('people',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('person_key', sa.String(length=90), nullable=False),
    sa.Column('given_name', sa.String(length=80), nullable=False),
    sa.Column('surnames', sa.String(length=120), nullable=False),
    sa.Column('birth_date', sa.Date(), nullable=False),
    sa.Column('origin_place_id', sa.String(length=32), nullable=False),
    sa.Column('nationalities', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('role', sa.String(length=24), nullable=False),
    sa.Column('primary_position', sa.String(length=4), nullable=False),
    sa.Column('secondary_positions', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('pitcher_role', sa.String(length=4), nullable=True),
    sa.Column('bats', sa.String(length=1), nullable=False),
    sa.Column('throws', sa.String(length=1), nullable=False),
    sa.Column('height_cm', sa.Integer(), nullable=False),
    sa.Column('weight_kg', sa.Integer(), nullable=False),
    sa.Column('attributes', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('overall', sa.Float(), nullable=False),
    sa.Column('state', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.ForeignKeyConstraint(['origin_place_id'], ['places.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('universe_id', 'person_key', name='uq_people_universe_key')
    )
    with op.batch_alter_table('people', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_people_universe_id'), ['universe_id'], unique=False)
        batch_op.create_index('ix_people_universe_overall', ['universe_id', 'overall'], unique=False)

    op.create_table('qualification_paths',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('source_competition_id', sa.String(length=32), nullable=False),
    sa.Column('target_competition_id', sa.String(length=32), nullable=False),
    sa.Column('slot_rule', sa.String(length=32), nullable=False),
    sa.Column('config', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.CheckConstraint('source_competition_id <> target_competition_id', name='ck_qualification_not_self'),
    sa.ForeignKeyConstraint(['source_competition_id'], ['competition_definitions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['target_competition_id'], ['competition_definitions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('qualification_paths', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_qualification_paths_universe_id'), ['universe_id'], unique=False)

    op.create_table('region_profiles',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('place_id', sa.String(length=32), nullable=False),
    sa.Column('ref_year', sa.Integer(), nullable=False),
    sa.Column('population', sa.BigInteger(), nullable=False),
    sa.Column('economy_index', sa.Float(), nullable=False),
    sa.Column('baseball_culture_index', sa.Float(), nullable=False),
    sa.Column('cost_of_living_index', sa.Float(), nullable=False),
    sa.Column('infrastructure_index', sa.Float(), nullable=False),
    sa.Column('confidence', sa.String(length=20), nullable=False),
    sa.Column('sources', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.ForeignKeyConstraint(['place_id'], ['places.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('place_id', 'ref_year', name='uq_region_profile_place_year')
    )
    with op.batch_alter_table('region_profiles', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_region_profiles_place_id'), ['place_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_region_profiles_universe_id'), ['universe_id'], unique=False)

    op.create_table('competition_editions',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('competition_id', sa.String(length=32), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('rules_version_id', sa.String(length=32), nullable=False),
    sa.Column('stage', sa.String(length=24), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('seed', sa.BigInteger(), nullable=False),
    sa.Column('sim_version', sa.String(length=32), nullable=False),
    sa.Column('champion_club_id', sa.String(length=32), nullable=True),
    sa.Column('warnings', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.ForeignKeyConstraint(['champion_club_id'], ['clubs.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['competition_id'], ['competition_definitions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['rules_version_id'], ['competition_rule_versions.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('competition_id', 'year', name='uq_edition_competition_year')
    )
    with op.batch_alter_table('competition_editions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_competition_editions_competition_id'), ['competition_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_competition_editions_universe_id'), ['universe_id'], unique=False)

    op.create_table('roster_assignments',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('club_id', sa.String(length=32), nullable=False),
    sa.Column('person_id', sa.String(length=32), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['person_id'], ['people.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('roster_assignments', schema=None) as batch_op:
        batch_op.create_index('ix_roster_active', ['universe_id', 'person_id', 'status'], unique=False)
        batch_op.create_index(batch_op.f('ix_roster_assignments_club_id'), ['club_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_roster_assignments_person_id'), ['person_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_roster_assignments_universe_id'), ['universe_id'], unique=False)

    op.create_table('venues',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('venue_key', sa.String(length=90), nullable=False),
    sa.Column('club_id', sa.String(length=32), nullable=True),
    sa.Column('place_id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=140), nullable=False),
    sa.Column('venue_type', sa.String(length=32), nullable=False),
    sa.Column('capacity', sa.Integer(), nullable=False),
    sa.Column('dimensions', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('surface', sa.String(length=24), nullable=False),
    sa.Column('elevation_m', sa.Integer(), nullable=False),
    sa.Column('lat', sa.Float(), nullable=False),
    sa.Column('lon', sa.Float(), nullable=False),
    sa.Column('has_roof', sa.Boolean(), nullable=False),
    sa.Column('maintenance', sa.Float(), nullable=False),
    sa.Column('built_year', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['place_id'], ['places.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('universe_id', 'venue_key', name='uq_venues_universe_key')
    )
    with op.batch_alter_table('venues', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_venues_universe_id'), ['universe_id'], unique=False)

    op.create_table('club_memberships',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('club_id', sa.String(length=32), nullable=False),
    sa.Column('competition_id', sa.String(length=32), nullable=False),
    sa.Column('membership_kind', sa.String(length=24), nullable=False),
    sa.Column('start_edition_id', sa.String(length=32), nullable=True),
    sa.Column('end_edition_id', sa.String(length=32), nullable=True),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['competition_id'], ['competition_definitions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['end_edition_id'], ['competition_editions.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['start_edition_id'], ['competition_editions.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('club_memberships', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_club_memberships_club_id'), ['club_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_club_memberships_competition_id'), ['competition_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_club_memberships_universe_id'), ['universe_id'], unique=False)

    op.create_table('edition_entries',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('edition_id', sa.String(length=32), nullable=False),
    sa.Column('participant_kind', sa.String(length=20), nullable=False),
    sa.Column('club_id', sa.String(length=32), nullable=True),
    sa.Column('seed_rank', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['edition_id'], ['competition_editions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('edition_id', 'club_id', name='uq_entry_edition_club')
    )
    with op.batch_alter_table('edition_entries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_edition_entries_edition_id'), ['edition_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_edition_entries_universe_id'), ['universe_id'], unique=False)

    op.create_table('playoff_series',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('edition_id', sa.String(length=32), nullable=False),
    sa.Column('series_key', sa.String(length=24), nullable=False),
    sa.Column('round_index', sa.Integer(), nullable=False),
    sa.Column('high_seed_club_id', sa.String(length=32), nullable=False),
    sa.Column('low_seed_club_id', sa.String(length=32), nullable=False),
    sa.Column('best_of', sa.Integer(), nullable=False),
    sa.Column('high_seed_wins', sa.Integer(), nullable=False),
    sa.Column('low_seed_wins', sa.Integer(), nullable=False),
    sa.Column('winner_club_id', sa.String(length=32), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.ForeignKeyConstraint(['edition_id'], ['competition_editions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['high_seed_club_id'], ['clubs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['low_seed_club_id'], ['clubs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['winner_club_id'], ['clubs.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('edition_id', 'series_key', name='uq_series_edition_key')
    )
    with op.batch_alter_table('playoff_series', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_playoff_series_edition_id'), ['edition_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_playoff_series_universe_id'), ['universe_id'], unique=False)

    op.create_table('games',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('edition_id', sa.String(length=32), nullable=False),
    sa.Column('stage', sa.String(length=24), nullable=False),
    sa.Column('round_index', sa.Integer(), nullable=False),
    sa.Column('series_key', sa.String(length=24), nullable=True),
    sa.Column('game_in_series', sa.Integer(), nullable=False),
    sa.Column('home_entry_id', sa.String(length=32), nullable=False),
    sa.Column('away_entry_id', sa.String(length=32), nullable=False),
    sa.Column('home_club_id', sa.String(length=32), nullable=False),
    sa.Column('away_club_id', sa.String(length=32), nullable=False),
    sa.Column('venue_id', sa.String(length=32), nullable=False),
    sa.Column('game_date', sa.Date(), nullable=False),
    sa.Column('state', sa.String(length=20), nullable=False),
    sa.Column('home_score', sa.Integer(), nullable=True),
    sa.Column('away_score', sa.Integer(), nullable=True),
    sa.Column('innings_played', sa.Integer(), nullable=True),
    sa.Column('line_score', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('weather', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('park_note', sa.String(length=80), nullable=False),
    sa.Column('engine_version', sa.String(length=40), nullable=True),
    sa.Column('seed', sa.BigInteger(), nullable=True),
    sa.ForeignKeyConstraint(['away_club_id'], ['clubs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['away_entry_id'], ['edition_entries.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['edition_id'], ['competition_editions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['home_club_id'], ['clubs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['home_entry_id'], ['edition_entries.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['venue_id'], ['venues.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('games', schema=None) as batch_op:
        batch_op.create_index('ix_games_edition_date', ['edition_id', 'game_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_games_edition_id'), ['edition_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_games_game_date'), ['game_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_games_universe_id'), ['universe_id'], unique=False)
        batch_op.create_index('ix_games_universe_state_date', ['universe_id', 'state', 'game_date'], unique=False)

    op.create_table('standings',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('edition_id', sa.String(length=32), nullable=False),
    sa.Column('entry_id', sa.String(length=32), nullable=False),
    sa.Column('wins', sa.Integer(), nullable=False),
    sa.Column('losses', sa.Integer(), nullable=False),
    sa.Column('ties', sa.Integer(), nullable=False),
    sa.Column('points', sa.Integer(), nullable=False),
    sa.Column('runs_for', sa.Integer(), nullable=False),
    sa.Column('runs_against', sa.Integer(), nullable=False),
    sa.Column('home_wins', sa.Integer(), nullable=False),
    sa.Column('home_losses', sa.Integer(), nullable=False),
    sa.Column('away_wins', sa.Integer(), nullable=False),
    sa.Column('away_losses', sa.Integer(), nullable=False),
    sa.Column('streak', sa.Integer(), nullable=False),
    sa.Column('last_ten', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.Column('rank', sa.Integer(), nullable=False),
    sa.Column('tiebreak_note', sa.String(length=80), nullable=False),
    sa.ForeignKeyConstraint(['edition_id'], ['competition_editions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['entry_id'], ['edition_entries.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('edition_id', 'entry_id', name='uq_standing_edition_entry')
    )
    with op.batch_alter_table('standings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_standings_edition_id'), ['edition_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_standings_universe_id'), ['universe_id'], unique=False)

    op.create_table('game_events',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('game_id', sa.String(length=32), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('event_type', sa.String(length=32), nullable=False),
    sa.Column('payload', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=False),
    sa.ForeignKeyConstraint(['game_id'], ['games.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('game_id', 'seq', name='uq_game_event_seq')
    )
    with op.batch_alter_table('game_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_game_events_game_id'), ['game_id'], unique=False)

    op.create_table('pitcher_game_stats',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('game_id', sa.String(length=32), nullable=False),
    sa.Column('edition_id', sa.String(length=32), nullable=False),
    sa.Column('person_id', sa.String(length=32), nullable=False),
    sa.Column('club_id', sa.String(length=32), nullable=False),
    sa.Column('is_starter', sa.Boolean(), nullable=False),
    sa.Column('outs_recorded', sa.Integer(), nullable=False),
    sa.Column('batters_faced', sa.Integer(), nullable=False),
    sa.Column('pitches', sa.Integer(), nullable=False),
    sa.Column('hits_allowed', sa.Integer(), nullable=False),
    sa.Column('runs_allowed', sa.Integer(), nullable=False),
    sa.Column('earned_runs', sa.Integer(), nullable=False),
    sa.Column('walks', sa.Integer(), nullable=False),
    sa.Column('hit_batsmen', sa.Integer(), nullable=False),
    sa.Column('strikeouts', sa.Integer(), nullable=False),
    sa.Column('home_runs_allowed', sa.Integer(), nullable=False),
    sa.Column('win', sa.Boolean(), nullable=False),
    sa.Column('loss', sa.Boolean(), nullable=False),
    sa.Column('save', sa.Boolean(), nullable=False),
    sa.Column('hold', sa.Boolean(), nullable=False),
    sa.CheckConstraint('earned_runs <= runs_allowed', name='ck_pitcher_er_le_r'),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['edition_id'], ['competition_editions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['game_id'], ['games.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['person_id'], ['people.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('game_id', 'person_id', name='uq_pitcher_stats_game_person')
    )
    with op.batch_alter_table('pitcher_game_stats', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pitcher_game_stats_edition_id'), ['edition_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pitcher_game_stats_game_id'), ['game_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pitcher_game_stats_person_id'), ['person_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pitcher_game_stats_universe_id'), ['universe_id'], unique=False)
        batch_op.create_index('ix_pitcher_stats_edition_person', ['edition_id', 'person_id'], unique=False)

    op.create_table('player_game_stats',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('game_id', sa.String(length=32), nullable=False),
    sa.Column('edition_id', sa.String(length=32), nullable=False),
    sa.Column('person_id', sa.String(length=32), nullable=False),
    sa.Column('club_id', sa.String(length=32), nullable=False),
    sa.Column('lineup_slot', sa.Integer(), nullable=False),
    sa.Column('position', sa.String(length=4), nullable=False),
    sa.Column('plate_appearances', sa.Integer(), nullable=False),
    sa.Column('at_bats', sa.Integer(), nullable=False),
    sa.Column('hits', sa.Integer(), nullable=False),
    sa.Column('singles', sa.Integer(), nullable=False),
    sa.Column('doubles', sa.Integer(), nullable=False),
    sa.Column('triples', sa.Integer(), nullable=False),
    sa.Column('home_runs', sa.Integer(), nullable=False),
    sa.Column('runs', sa.Integer(), nullable=False),
    sa.Column('runs_batted_in', sa.Integer(), nullable=False),
    sa.Column('walks', sa.Integer(), nullable=False),
    sa.Column('hit_by_pitch', sa.Integer(), nullable=False),
    sa.Column('strikeouts', sa.Integer(), nullable=False),
    sa.Column('sac_flies', sa.Integer(), nullable=False),
    sa.Column('stolen_bases', sa.Integer(), nullable=False),
    sa.Column('caught_stealing', sa.Integer(), nullable=False),
    sa.Column('reached_on_error', sa.Integer(), nullable=False),
    sa.Column('errors', sa.Integer(), nullable=False),
    sa.Column('putouts', sa.Integer(), nullable=False),
    sa.Column('assists', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['edition_id'], ['competition_editions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['game_id'], ['games.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['person_id'], ['people.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('game_id', 'person_id', name='uq_player_stats_game_person')
    )
    with op.batch_alter_table('player_game_stats', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_player_game_stats_edition_id'), ['edition_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_player_game_stats_game_id'), ['game_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_player_game_stats_person_id'), ['person_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_player_game_stats_universe_id'), ['universe_id'], unique=False)
        batch_op.create_index('ix_player_stats_edition_person', ['edition_id', 'person_id'], unique=False)

    op.create_table('team_game_stats',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('universe_id', sa.String(length=32), nullable=False),
    sa.Column('game_id', sa.String(length=32), nullable=False),
    sa.Column('club_id', sa.String(length=32), nullable=False),
    sa.Column('is_home', sa.Boolean(), nullable=False),
    sa.Column('runs', sa.Integer(), nullable=False),
    sa.Column('hits', sa.Integer(), nullable=False),
    sa.Column('errors', sa.Integer(), nullable=False),
    sa.Column('left_on_base', sa.Integer(), nullable=False),
    sa.Column('outs_suffered', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['game_id'], ['games.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('game_id', 'club_id', name='uq_team_stats_game_club')
    )
    with op.batch_alter_table('team_game_stats', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_team_game_stats_game_id'), ['game_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_team_game_stats_universe_id'), ['universe_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('team_game_stats', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_team_game_stats_universe_id'))
        batch_op.drop_index(batch_op.f('ix_team_game_stats_game_id'))

    op.drop_table('team_game_stats')
    with op.batch_alter_table('player_game_stats', schema=None) as batch_op:
        batch_op.drop_index('ix_player_stats_edition_person')
        batch_op.drop_index(batch_op.f('ix_player_game_stats_universe_id'))
        batch_op.drop_index(batch_op.f('ix_player_game_stats_person_id'))
        batch_op.drop_index(batch_op.f('ix_player_game_stats_game_id'))
        batch_op.drop_index(batch_op.f('ix_player_game_stats_edition_id'))

    op.drop_table('player_game_stats')
    with op.batch_alter_table('pitcher_game_stats', schema=None) as batch_op:
        batch_op.drop_index('ix_pitcher_stats_edition_person')
        batch_op.drop_index(batch_op.f('ix_pitcher_game_stats_universe_id'))
        batch_op.drop_index(batch_op.f('ix_pitcher_game_stats_person_id'))
        batch_op.drop_index(batch_op.f('ix_pitcher_game_stats_game_id'))
        batch_op.drop_index(batch_op.f('ix_pitcher_game_stats_edition_id'))

    op.drop_table('pitcher_game_stats')
    with op.batch_alter_table('game_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_game_events_game_id'))

    op.drop_table('game_events')
    with op.batch_alter_table('standings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_standings_universe_id'))
        batch_op.drop_index(batch_op.f('ix_standings_edition_id'))

    op.drop_table('standings')
    with op.batch_alter_table('games', schema=None) as batch_op:
        batch_op.drop_index('ix_games_universe_state_date')
        batch_op.drop_index(batch_op.f('ix_games_universe_id'))
        batch_op.drop_index(batch_op.f('ix_games_game_date'))
        batch_op.drop_index(batch_op.f('ix_games_edition_id'))
        batch_op.drop_index('ix_games_edition_date')

    op.drop_table('games')
    with op.batch_alter_table('playoff_series', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_playoff_series_universe_id'))
        batch_op.drop_index(batch_op.f('ix_playoff_series_edition_id'))

    op.drop_table('playoff_series')
    with op.batch_alter_table('edition_entries', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_edition_entries_universe_id'))
        batch_op.drop_index(batch_op.f('ix_edition_entries_edition_id'))

    op.drop_table('edition_entries')
    with op.batch_alter_table('club_memberships', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_club_memberships_universe_id'))
        batch_op.drop_index(batch_op.f('ix_club_memberships_competition_id'))
        batch_op.drop_index(batch_op.f('ix_club_memberships_club_id'))

    op.drop_table('club_memberships')
    with op.batch_alter_table('venues', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_venues_universe_id'))

    op.drop_table('venues')
    with op.batch_alter_table('roster_assignments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_roster_assignments_universe_id'))
        batch_op.drop_index(batch_op.f('ix_roster_assignments_person_id'))
        batch_op.drop_index(batch_op.f('ix_roster_assignments_club_id'))
        batch_op.drop_index('ix_roster_active')

    op.drop_table('roster_assignments')
    with op.batch_alter_table('competition_editions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_competition_editions_universe_id'))
        batch_op.drop_index(batch_op.f('ix_competition_editions_competition_id'))

    op.drop_table('competition_editions')
    with op.batch_alter_table('region_profiles', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_region_profiles_universe_id'))
        batch_op.drop_index(batch_op.f('ix_region_profiles_place_id'))

    op.drop_table('region_profiles')
    with op.batch_alter_table('qualification_paths', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_qualification_paths_universe_id'))

    op.drop_table('qualification_paths')
    with op.batch_alter_table('people', schema=None) as batch_op:
        batch_op.drop_index('ix_people_universe_overall')
        batch_op.drop_index(batch_op.f('ix_people_universe_id'))

    op.drop_table('people')
    with op.batch_alter_table('competition_rule_versions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_competition_rule_versions_universe_id'))
        batch_op.drop_index(batch_op.f('ix_competition_rule_versions_competition_id'))

    op.drop_table('competition_rule_versions')
    with op.batch_alter_table('competition_relationships', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_competition_relationships_universe_id'))

    op.drop_table('competition_relationships')
    with op.batch_alter_table('clubs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_clubs_universe_id'))

    op.drop_table('clubs')
    with op.batch_alter_table('simulation_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_simulation_events_world_date'))
        batch_op.drop_index(batch_op.f('ix_simulation_events_universe_id'))
        batch_op.drop_index('ix_sim_events_universe_date')

    op.drop_table('simulation_events')
    with op.batch_alter_table('simulation_commands', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_simulation_commands_universe_id'))

    op.drop_table('simulation_commands')
    with op.batch_alter_table('sim_jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sim_jobs_universe_id'))

    op.drop_table('sim_jobs')
    with op.batch_alter_table('places', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_places_universe_id'))

    op.drop_table('places')
    with op.batch_alter_table('generation_provenance', schema=None) as batch_op:
        batch_op.drop_index('ix_provenance_universe_entity')
        batch_op.drop_index(batch_op.f('ix_generation_provenance_universe_id'))

    op.drop_table('generation_provenance')
    with op.batch_alter_table('competition_definitions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_competition_definitions_universe_id'))

    op.drop_table('competition_definitions')
    op.drop_table('universes')
