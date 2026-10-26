"""personas del universo: perfil universal y oficio deportivo opcional

Revision ID: c3e2a8b14d67
Revises: b2d1f7a93c54
Create Date: 2026-10-25

Primer hito del anexo de personas que toca la base. Dos cambios, y los dos
vienen del mismo hallazgo de la auditoría H0: hasta ahora **toda persona tenía
que ser un jugador**.

1. `person_universal_profiles`: los 52 atributos universales, en JSONB
   validado, con la versión del catálogo con la que nacieron y la semilla de la
   que salieron. Uno por persona; la clave primaria es la persona.

2. Las columnas deportivas de `people` pasan a admitir nulo: posición,
   lateralidad, estatura, peso, valoración global y el papel heredado. Un
   tesorero, una coordinadora o una estudiante no tienen posición de juego, y
   antes el esquema no las dejaba existir.

No hay relleno de datos aquí a propósito. Las personas que ya existen reciben
su perfil la primera vez que alguien lo pide (`person_service.ensure_profile`),
con los números que el universo ya conocía conservados; una migración de datos
tendría que importar el generador de la simulación para hacer lo mismo peor.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3e2a8b14d67"
down_revision = "b2d1f7a93c54"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "person_universal_profiles",
        sa.Column("person_id", sa.String(length=32), nullable=False),
        sa.Column("universe_id", sa.String(length=32), nullable=False),
        sa.Column("profile_schema_version", sa.Integer(), nullable=False),
        sa.Column("profile_data", sa.JSON(), nullable=False),
        sa.Column("generated_seed", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("parameter_version", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("origin", sa.String(length=16), nullable=False, server_default="generated"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["person_id"], ["people.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["universe_id"], ["universes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("person_id"),
    )
    op.create_index(
        "ix_person_universal_profiles_universe_id",
        "person_universal_profiles",
        ["universe_id"],
    )

    with op.batch_alter_table("people") as batch:
        batch.alter_column("role", existing_type=sa.String(length=24), nullable=True)
        batch.alter_column("primary_position", existing_type=sa.String(length=4), nullable=True)
        batch.alter_column("bats", existing_type=sa.String(length=1), nullable=True)
        batch.alter_column("throws", existing_type=sa.String(length=1), nullable=True)
        batch.alter_column("height_cm", existing_type=sa.Integer(), nullable=True)
        batch.alter_column("weight_kg", existing_type=sa.Integer(), nullable=True)
        batch.alter_column("overall", existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    # Volver atrás exige que no haya personas sin oficio deportivo: sus
    # columnas no admitirían nulo. Se dejan fuera las que no se puedan
    # completar en vez de inventarles una posición de juego.
    op.execute(
        "DELETE FROM people WHERE primary_position IS NULL OR overall IS NULL "
        "OR bats IS NULL OR throws IS NULL OR height_cm IS NULL OR weight_kg IS NULL"
    )
    op.execute("UPDATE people SET role = 'player' WHERE role IS NULL")
    with op.batch_alter_table("people") as batch:
        batch.alter_column("overall", existing_type=sa.Float(), nullable=False)
        batch.alter_column("weight_kg", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("height_cm", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("throws", existing_type=sa.String(length=1), nullable=False)
        batch.alter_column("bats", existing_type=sa.String(length=1), nullable=False)
        batch.alter_column("primary_position", existing_type=sa.String(length=4), nullable=False)
        batch.alter_column("role", existing_type=sa.String(length=24), nullable=False)
    op.drop_index(
        "ix_person_universal_profiles_universe_id", table_name="person_universal_profiles"
    )
    op.drop_table("person_universal_profiles")
