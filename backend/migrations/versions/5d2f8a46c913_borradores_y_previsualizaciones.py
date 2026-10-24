"""borradores de competición y previsualizaciones inmutables con huella

Revision ID: 5d2f8a46c913
Revises: 4c9e13a7b250
Create Date: 2026-10-23

Fase P4 del FIX V2 de Fase 1. Dos tablas que separan **lo que el usuario está
escribiendo** de **lo que el generador propuso**:

- `competition_drafts`: la intención, su estado en el ciclo
  `draft → … → committed` y la huella SHA-256 de la intención canónica. Cambiar
  una regla cambia la huella, y eso invalida la propuesta anterior.
- `generation_previews`: la propuesta, inmutable, con los clubes candidatos, su
  contexto y los problemas detectados. **No** contiene entidades del mundo:
  previsualizar no escribe nada.

Al confirmar se exige la huella, así que no se puede crear un mundo distinto del
que se vio.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision = '5d2f8a46c913'
down_revision = '4c9e13a7b250'
branch_labels = None
depends_on = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql')


def upgrade() -> None:
    op.create_table(
        'competition_drafts',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('universe_id', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('state', sa.String(length=24), nullable=False),
        sa.Column('intent', JSON_TYPE, nullable=False),
        sa.Column('intent_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('preview_id', sa.String(length=32), nullable=True),
        sa.Column('competition_id', sa.String(length=32), nullable=True),
        sa.Column('issues', JSON_TYPE, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['competition_id'], ['competition_definitions.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_competition_drafts_universe_id', 'competition_drafts', ['universe_id'])

    op.create_table(
        'generation_previews',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('universe_id', sa.String(length=32), nullable=False),
        sa.Column('draft_id', sa.String(length=32), nullable=True),
        sa.Column('intent_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('ruleset_checksum', sa.String(length=64), nullable=False),
        sa.Column('engine_version', sa.String(length=32), nullable=False),
        sa.Column('seed', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('context', JSON_TYPE, nullable=False),
        sa.Column('candidates', JSON_TYPE, nullable=False),
        sa.Column('issues', JSON_TYPE, nullable=False),
        sa.Column('committed_competition_id', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['universe_id'], ['universes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['draft_id'], ['competition_drafts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['committed_competition_id'], ['competition_definitions.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_generation_previews_universe_id', 'generation_previews', ['universe_id'])
    op.create_index('ix_generation_previews_draft_id', 'generation_previews', ['draft_id'])
    op.create_index(
        'ix_preview_fingerprint', 'generation_previews', ['universe_id', 'intent_fingerprint']
    )


def downgrade() -> None:
    op.drop_index('ix_preview_fingerprint', table_name='generation_previews')
    op.drop_index('ix_generation_previews_draft_id', table_name='generation_previews')
    op.drop_index('ix_generation_previews_universe_id', table_name='generation_previews')
    op.drop_table('generation_previews')
    op.drop_index('ix_competition_drafts_universe_id', table_name='competition_drafts')
    op.drop_table('competition_drafts')
