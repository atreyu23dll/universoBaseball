"""Fases encadenadas: una clasificación por fase

Una liguilla entre los clasificados tiene **su propia tabla**: empieza de cero
y no arrastra los partidos de la fase anterior. Por eso la clasificación pasa a
ser una fila por (edición, participante, fase) y la edición recuerda en qué
fase de la secuencia está.

Las ediciones existentes quedan con `stage_index = 0` y sus filas de
clasificación con `stage_key = 'regular_season'`, que es exactamente la fase que
estaban jugando.

Revision ID: 9b3d7e21a648
Revises: 8a2c6b47e135
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "9b3d7e21a648"
down_revision = "8a2c6b47e135"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "competition_editions",
        sa.Column("stage_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "standings",
        sa.Column(
            "stage_key",
            sa.String(length=40),
            nullable=False,
            server_default="regular_season",
        ),
    )
    # La clave única gana la fase. `batch_alter_table` es obligatorio en SQLite,
    # que no sabe soltar una constraint sin reconstruir la tabla.
    with op.batch_alter_table("standings") as batch:
        batch.drop_constraint("uq_standing_edition_entry", type_="unique")
        batch.create_unique_constraint(
            "uq_standing_edition_entry_stage", ["edition_id", "entry_id", "stage_key"]
        )


def downgrade() -> None:
    # Volver atrás solo es posible si ninguna edición jugó más de una fase: dos
    # filas del mismo participante chocarían con la clave antigua. Se borran
    # las de las fases posteriores, y eso es una pérdida de información que se
    # declara en vez de disimularse.
    op.execute("DELETE FROM standings WHERE stage_key <> 'regular_season'")
    with op.batch_alter_table("standings") as batch:
        batch.drop_constraint("uq_standing_edition_entry_stage", type_="unique")
        batch.create_unique_constraint(
            "uq_standing_edition_entry", ["edition_id", "entry_id"]
        )
    op.drop_column("standings", "stage_key")
    op.drop_column("competition_editions", "stage_index")
