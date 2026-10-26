"""organigrama de cada club: unidades, cargos y responsabilidades N:M

Revision ID: d4f1b7c25e38
Revises: c3e2a8b14d67
Create Date: 2026-10-26

Implementa la plantilla de organigrama: cinco familias funcionales de primer
nivel divisibles en subdivisiones sin límite de profundidad, cargos que pueden
quedar **vacantes** y un vínculo **N:M** entre personas y unidades —una unidad
con varias personas, una persona en varias unidades y varios clubes—.

Tres tablas y ninguna columna nueva en `clubs`: el organigrama no es un campo
del club, es una estructura con su propia historia. `reason` en las tres porque
la plantilla exige que primero existan las necesidades y después la estructura,
y eso solo se puede comprobar si cada unidad dice qué necesidad la justificó.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d4f1b7c25e38"
down_revision = "c3e2a8b14d67"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_units",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("universe_id", sa.String(length=32), nullable=False),
        sa.Column("club_id", sa.String(length=32), nullable=False),
        sa.Column("parent_unit_id", sa.String(length=32), nullable=True),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("functional_family", sa.String(length=24), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("formed_season", sa.Integer(), nullable=False),
        sa.Column("closed_season", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["universe_id"], ["universes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parent_unit_id"], ["organization_units.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("club_id", "code", name="uq_org_unit_club_code"),
    )
    op.create_index("ix_organization_units_universe_id", "organization_units", ["universe_id"])
    op.create_index("ix_organization_units_club_id", "organization_units", ["club_id"])
    op.create_index("ix_org_units_parent", "organization_units", ["club_id", "parent_unit_id"])

    op.create_table(
        "organization_positions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("universe_id", sa.String(length=32), nullable=False),
        sa.Column("club_id", sa.String(length=32), nullable=False),
        sa.Column("unit_id", sa.String(length=32), nullable=False),
        sa.Column("function_code", sa.String(length=48), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("max_occupants", sa.Integer(), nullable=True),
        sa.Column("authority", sa.JSON(), nullable=False),
        sa.Column(
            "commitment_hours_week", sa.Float(), nullable=False, server_default="0"
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["universe_id"], ["universes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["unit_id"], ["organization_units.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "club_id", "unit_id", "function_code", name="uq_org_position_unit_code"
        ),
    )
    op.create_index(
        "ix_organization_positions_universe_id", "organization_positions", ["universe_id"]
    )
    op.create_index("ix_organization_positions_club_id", "organization_positions", ["club_id"])
    op.create_index("ix_organization_positions_unit_id", "organization_positions", ["unit_id"])

    op.create_table(
        "organization_role_assignments",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("universe_id", sa.String(length=32), nullable=False),
        sa.Column("person_id", sa.String(length=32), nullable=False),
        sa.Column("club_id", sa.String(length=32), nullable=False),
        sa.Column("unit_id", sa.String(length=32), nullable=False),
        sa.Column("position_id", sa.String(length=32), nullable=True),
        sa.Column("function_code", sa.String(length=48), nullable=False),
        sa.Column("authority", sa.JSON(), nullable=False),
        sa.Column(
            "commitment_hours_week", sa.Float(), nullable=False, server_default="0"
        ),
        sa.Column("arrangement", sa.String(length=32), nullable=False, server_default="volunteer"),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["universe_id"], ["universes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["people.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["unit_id"], ["organization_units.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["position_id"], ["organization_positions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_organization_role_assignments_universe_id",
        "organization_role_assignments",
        ["universe_id"],
    )
    op.create_index(
        "ix_organization_role_assignments_person_id",
        "organization_role_assignments",
        ["person_id"],
    )
    op.create_index(
        "ix_organization_role_assignments_club_id", "organization_role_assignments", ["club_id"]
    )
    op.create_index(
        "ix_organization_role_assignments_unit_id", "organization_role_assignments", ["unit_id"]
    )
    op.create_index(
        "ix_org_roles_person", "organization_role_assignments", ["universe_id", "person_id", "status"]
    )
    op.create_index("ix_org_roles_unit", "organization_role_assignments", ["unit_id", "status"])


def downgrade() -> None:
    op.drop_table("organization_role_assignments")
    op.drop_table("organization_positions")
    op.drop_table("organization_units")
