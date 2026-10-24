"""gazetteer mundial: GeoNames, monedas por jurisdicción y límites de geoBoundaries

Revision ID: 4c9e13a7b250
Revises: 3b8d52c1f047
Create Date: 2026-10-22

Fase P2 del FIX V2 de Fase 1. Tres tablas de **datos de referencia**, no de un
universo concreto: el mundo es el mismo para todas las partidas.

- `gazetteer_countries`: países con su ISO, su moneda de curso legal (ISO 4217,
  vía `countryInfo.txt`) y, donde esté curado, el coste mensual de referencia que
  permite convertir índices en importes.
- `gazetteer_entities`: localidades y divisiones administrativas con
  identificador propio y referencia externa estable (`source` + `source_id`), de
  modo que reimportar no duplica y cada lugar se puede rastrear a su fuente.
- `gazetteer_boundaries`: límites administrativos **solo donde la fuente los
  publica**, con su licencia y su año. Sin fila no hay polígono, y la
  competición se delimita por contención administrativa o por radio.

En PostgreSQL se crea además un índice GIN de trigramas sobre el texto de
búsqueda si la extensión `pg_trgm` está disponible, que es lo que hace que
buscar «kampala» entre 236.000 localidades sea instantáneo. Si no está, se
degrada a búsqueda por prefijo y se dice en el log: no se exige una extensión
para poder arrancar.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision = '4c9e13a7b250'
down_revision = '3b8d52c1f047'
branch_labels = None
depends_on = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql')
MONEY = sa.Numeric(16, 2)


def upgrade() -> None:
    op.create_table(
        'gazetteer_countries',
        sa.Column('iso2', sa.String(length=2), nullable=False),
        sa.Column('iso3', sa.String(length=3), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('capital', sa.String(length=120), nullable=False),
        sa.Column('continent', sa.String(length=2), nullable=False),
        sa.Column('currency_code', sa.String(length=3), nullable=True),
        sa.Column('currency_name', sa.String(length=60), nullable=True),
        sa.Column('population', sa.BigInteger(), nullable=False),
        sa.Column('area_km2', sa.Float(), nullable=True),
        sa.Column('geoname_id', sa.BigInteger(), nullable=True),
        sa.Column('languages', JSON_TYPE, nullable=False),
        sa.Column('reference_monthly_cost', MONEY, nullable=True),
        sa.Column('reference_cost_year', sa.Integer(), nullable=True),
        sa.Column('reference_cost_sources', JSON_TYPE, nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('imported_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('iso2'),
    )

    op.create_table(
        'gazetteer_entities',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('source_id', sa.String(length=32), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('ascii_name', sa.String(length=200), nullable=False),
        sa.Column('search_text', sa.Text(), nullable=False),
        sa.Column('variants', JSON_TYPE, nullable=False),
        sa.Column('country_iso2', sa.String(length=2), nullable=False),
        sa.Column('admin1_code', sa.String(length=24), nullable=True),
        sa.Column('admin2_code', sa.String(length=48), nullable=True),
        sa.Column('parent_id', sa.String(length=32), nullable=True),
        sa.Column('lat', sa.Float(), nullable=False),
        sa.Column('lon', sa.Float(), nullable=False),
        sa.Column('elevation_m', sa.Integer(), nullable=False),
        sa.Column('population', sa.BigInteger(), nullable=False),
        sa.Column('feature_class', sa.String(length=4), nullable=False),
        sa.Column('feature_code', sa.String(length=12), nullable=False),
        sa.Column('timezone', sa.String(length=64), nullable=False),
        sa.Column('resolution_status', sa.String(length=16), nullable=False),
        sa.Column('resolution_notes', JSON_TYPE, nullable=False),
        sa.Column('imported_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['parent_id'], ['gazetteer_entities.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', 'source_id', name='uq_gazetteer_source_id'),
    )
    op.create_index('ix_gazetteer_entities_country_iso2', 'gazetteer_entities', ['country_iso2'])
    op.create_index('ix_gazetteer_search', 'gazetteer_entities', ['search_text'])
    op.create_index(
        'ix_gazetteer_country_kind', 'gazetteer_entities', ['country_iso2', 'kind']
    )

    op.create_table(
        'gazetteer_boundaries',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('entity_id', sa.String(length=32), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('source_id', sa.String(length=64), nullable=False),
        sa.Column('admin_level', sa.String(length=8), nullable=False),
        sa.Column('geometry', JSON_TYPE, nullable=False),
        sa.Column('crs', sa.String(length=16), nullable=False),
        sa.Column('licence', sa.String(length=160), nullable=False),
        sa.Column('licence_source', sa.String(length=200), nullable=False),
        sa.Column('represented_year', sa.String(length=16), nullable=False),
        sa.Column('downloaded_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['entity_id'], ['gazetteer_entities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('entity_id', 'source', 'admin_level', name='uq_boundary_entity_level'),
    )
    op.create_index('ix_gazetteer_boundaries_entity_id', 'gazetteer_boundaries', ['entity_id'])

    with op.batch_alter_table('places') as batch:
        batch.add_column(sa.Column('gazetteer_entity_id', sa.String(length=32), nullable=True))

    with op.batch_alter_table('competition_definitions') as batch:
        batch.add_column(
            sa.Column('territory_entity_ids', JSON_TYPE, nullable=False, server_default='[]')
        )

    _create_trigram_index()


def _create_trigram_index() -> None:
    """Índice de trigramas en PostgreSQL, si la extensión está disponible.

    No se exige: un arranque en SQLite o un PostgreSQL sin `pg_trgm` siguen
    funcionando con búsqueda por prefijo, más lenta pero correcta.
    """
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return
    try:
        op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
        op.execute(
            'CREATE INDEX IF NOT EXISTS ix_gazetteer_search_trgm '
            'ON gazetteer_entities USING gin (search_text gin_trgm_ops)'
        )
    except Exception:  # pragma: no cover - depende de permisos del servidor
        # Sin permiso para crear extensiones: se sigue con el índice normal.
        pass


def downgrade() -> None:
    with op.batch_alter_table('competition_definitions') as batch:
        batch.drop_column('territory_entity_ids')
    with op.batch_alter_table('places') as batch:
        batch.drop_column('gazetteer_entity_id')
    op.drop_index('ix_gazetteer_boundaries_entity_id', table_name='gazetteer_boundaries')
    op.drop_table('gazetteer_boundaries')
    op.drop_index('ix_gazetteer_country_kind', table_name='gazetteer_entities')
    op.drop_index('ix_gazetteer_search', table_name='gazetteer_entities')
    op.drop_index('ix_gazetteer_entities_country_iso2', table_name='gazetteer_entities')
    op.drop_table('gazetteer_entities')
    op.drop_table('gazetteer_countries')
