"""catálogo mundial de universidades reales para ligas escolares adultas

Revision ID: a1c0e9d4b76f
Revises: 9b3d7e21a648
Create Date: 2026-10-24

El catálogo no pertenece a un universo: es una referencia importada y trazable
desde GeoNames. Las ligas guardan el subconjunto que vieron al previsualizar,
por lo que una edición no vuelve a consultar la red ni inventa equipos para
rellenar una cifra.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1c0e9d4b76f"
down_revision = "9b3d7e21a648"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "educational_institutions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=220), nullable=False),
        sa.Column("ascii_name", sa.String(length=220), nullable=False, server_default=""),
        sa.Column("country_iso2", sa.String(length=2), nullable=False),
        sa.Column("admin1_code", sa.String(length=24), nullable=True),
        sa.Column("admin2_code", sa.String(length=48), nullable=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("source_url", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("licence", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_id", name="uq_education_source_id"),
    )
    op.create_index(
        "ix_educational_institutions_country_iso2",
        "educational_institutions",
        ["country_iso2"],
    )
    op.create_index(
        "ix_education_country_admin",
        "educational_institutions",
        ["country_iso2", "admin1_code", "admin2_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_education_country_admin", table_name="educational_institutions")
    op.drop_index("ix_educational_institutions_country_iso2", table_name="educational_institutions")
    op.drop_table("educational_institutions")
