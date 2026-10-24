"""libro mayor por temporada e historia institucional de los clubes

Revision ID: 6e4b91d7c825
Revises: 5d2f8a46c913
Create Date: 2026-10-23

Fase P5 del FIX V2 de Fase 1: las instituciones dejan de quedarse congeladas al
generarse.

- `club_season_ledgers`: lo que cada club **cobró y pagó** en una temporada,
  asiento por asiento, con lo que esperaba al lado. Clave única por club y
  temporada: reintentar un avance no liquida dos veces.
- `club_organization_changes`: la historia de su organización —gobierno, sede,
  base social— con la causa de cada cambio. No se sobrescribe el pasado.
- `clubs.seasons_insolvent`: temporadas consecutivas sin cuadrar. Una mala no
  cierra un club; dos seguidas, sí.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision = '6e4b91d7c825'
down_revision = '5d2f8a46c913'
branch_labels = None
depends_on = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql')
MONEY = sa.Numeric(16, 2)


def upgrade() -> None:
    op.create_table(
        'club_season_ledgers',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('universe_id', sa.String(length=32), nullable=False),
        sa.Column('club_id', sa.String(length=32), nullable=False),
        sa.Column('competition_id', sa.String(length=32), nullable=True),
        sa.Column('season', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=8), nullable=True),
        sa.Column('collected', MONEY, nullable=False),
        sa.Column('paid', MONEY, nullable=False),
        sa.Column('result', MONEY, nullable=False),
        sa.Column('cash_start', MONEY, nullable=False),
        sa.Column('cash_end', MONEY, nullable=False),
        sa.Column('debt_start', MONEY, nullable=False),
        sa.Column('debt_end', MONEY, nullable=False),
        sa.Column('outcome', sa.String(length=16), nullable=False),
        sa.Column('entries', JSON_TYPE, nullable=False),
        sa.Column('notes', JSON_TYPE, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['competition_id'], ['competition_definitions.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('club_id', 'season', name='uq_ledger_club_season'),
    )
    op.create_index('ix_club_season_ledgers_universe_id', 'club_season_ledgers', ['universe_id'])
    op.create_index('ix_club_season_ledgers_club_id', 'club_season_ledgers', ['club_id'])
    op.create_index('ix_ledger_universe_season', 'club_season_ledgers', ['universe_id', 'season'])

    op.create_table(
        'club_organization_changes',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('universe_id', sa.String(length=32), nullable=False),
        sa.Column('club_id', sa.String(length=32), nullable=False),
        sa.Column('season', sa.Integer(), nullable=False),
        sa.Column('field', sa.String(length=40), nullable=False),
        sa.Column('before', sa.String(length=120), nullable=False),
        sa.Column('after', sa.String(length=120), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_club_organization_changes_universe_id', 'club_organization_changes', ['universe_id']
    )
    op.create_index(
        'ix_club_organization_changes_club_id', 'club_organization_changes', ['club_id']
    )

    with op.batch_alter_table('clubs') as batch:
        batch.add_column(
            sa.Column('seasons_insolvent', sa.Integer(), nullable=False, server_default='0')
        )


def downgrade() -> None:
    with op.batch_alter_table('clubs') as batch:
        batch.drop_column('seasons_insolvent')
    op.drop_index('ix_club_organization_changes_club_id', table_name='club_organization_changes')
    op.drop_index(
        'ix_club_organization_changes_universe_id', table_name='club_organization_changes'
    )
    op.drop_table('club_organization_changes')
    op.drop_index('ix_ledger_universe_season', table_name='club_season_ledgers')
    op.drop_index('ix_club_season_ledgers_club_id', table_name='club_season_ledgers')
    op.drop_index('ix_club_season_ledgers_universe_id', table_name='club_season_ledgers')
    op.drop_table('club_season_ledgers')
