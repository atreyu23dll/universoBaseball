"""Playoffs con pase directo: plazas que no son potencia de dos

Con seis clasificados —dos campeones de división y dos repechajes, que es lo
natural en una competición con divisiones— el cuadro es de ocho y dos siembras
esperan en la segunda ronda. Esos clubes se guardan aquí porque la ronda
siguiente se construye otro día y en otra transacción.

Revision ID: 8a2c6b47e135
Revises: 7f1a5c38d904
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")

revision = "8a2c6b47e135"
down_revision = "7f1a5c38d904"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "competition_editions",
        sa.Column("playoff_byes", JSON_TYPE, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("competition_editions", "playoff_byes")
