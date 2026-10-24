"""movilidad entre competiciones: temporadas de pertenencia y transiciones

Revision ID: 2a7c41b0e9d2
Revises: 1df364013388
Create Date: 2026-10-21

La pertenencia de un club a una competición pasa a tener vigencia por
temporadas: un ascenso se resuelve cuando la edición de destino todavía no
existe, así que `start_edition_id` no basta para decir «este club juega la
liga de arriba a partir del año que viene».

`season_transitions` es el libro de cierres ya aplicados; su clave única hace
idempotente el intercambio de clubes.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision = '2a7c41b0e9d2'
down_revision = '1df364013388'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('club_memberships') as batch:
        batch.add_column(sa.Column('start_season', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('end_season', sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column(
                'origin', sa.String(length=24), nullable=False, server_default='generated'
            )
        )
    op.create_index(
        'ix_membership_competition_season',
        'club_memberships',
        ['competition_id', 'start_season', 'end_season'],
    )

    # Las pertenencias que ya existen vienen de la generación inicial: su
    # temporada de inicio es el año de la edición con la que nacieron.
    op.execute(
        """
        UPDATE club_memberships
           SET start_season = (
                 SELECT year FROM competition_editions
                  WHERE competition_editions.id = club_memberships.start_edition_id
               )
         WHERE start_edition_id IS NOT NULL
        """
    )

    op.create_table(
        'season_transitions',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('universe_id', sa.String(length=32), nullable=False),
        sa.Column('upper_competition_id', sa.String(length=32), nullable=False),
        sa.Column('season', sa.Integer(), nullable=False),
        sa.Column('applied_on', sa.Date(), nullable=False),
        sa.Column(
            'plan',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'),
            nullable=False,
        ),
        sa.Column('promotions', sa.Integer(), nullable=False),
        sa.Column('relegations', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['upper_competition_id'], ['competition_definitions.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'upper_competition_id', 'season', name='uq_transition_competition_season'
        ),
    )
    op.create_index(
        'ix_season_transitions_universe_id', 'season_transitions', ['universe_id']
    )


def downgrade() -> None:
    op.drop_index('ix_season_transitions_universe_id', table_name='season_transitions')
    op.drop_table('season_transitions')
    op.drop_index('ix_membership_competition_season', table_name='club_memberships')
    with op.batch_alter_table('club_memberships') as batch:
        batch.drop_column('origin')
        batch.drop_column('end_season')
        batch.drop_column('start_season')
