"""catálogo universitario mundial sin descargas

Revision ID: b2d1f7a93c54
Revises: a1c0e9d4b76f
Create Date: 2026-10-25

El catálogo deja de extraerse del volcado completo de GeoNames —422 MB para
mil quinientas universidades mal repartidas— y pasa a leerse de un fichero
versionado con el repositorio. Cada institución trae ahora qué clase de centro
es, su año de fundación y su web cuando la fuente los publica, y la localidad
del gazetteer que la sitúa, que es la que resuelve a qué territorio pertenece.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b2d1f7a93c54"
down_revision = "a1c0e9d4b76f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "educational_institutions",
        sa.Column("institution_type", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "educational_institutions", sa.Column("founded_year", sa.Integer(), nullable=True)
    )
    op.add_column(
        "educational_institutions", sa.Column("website", sa.String(length=300), nullable=True)
    )
    op.add_column(
        "educational_institutions", sa.Column("locality_name", sa.String(length=200), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("educational_institutions", "locality_name")
    op.drop_column("educational_institutions", "website")
    op.drop_column("educational_institutions", "founded_year")
    op.drop_column("educational_institutions", "institution_type")
