"""Grupos, divisiones y conferencias dentro de una competición

El grupo se guarda en la inscripción de la edición (`edition_entries`) y no en
el club, porque el reparto se rehace cada temporada: un club que asciende
cambia de división sin dejar de ser el mismo club. Las ediciones ya jugadas
quedan con el grupo vacío, que es exactamente lo que fueron: competiciones de
tabla única.

Revision ID: 7f1a5c38d904
Revises: 6e4b91d7c825
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "7f1a5c38d904"
down_revision = "6e4b91d7c825"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "edition_entries",
        sa.Column("group_key", sa.String(length=40), nullable=False, server_default=""),
    )
    op.add_column(
        "standings",
        sa.Column("group_rank", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_entries_edition_group",
        "edition_entries",
        ["edition_id", "group_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_entries_edition_group", table_name="edition_entries")
    op.drop_column("standings", "group_rank")
    op.drop_column("edition_entries", "group_key")
