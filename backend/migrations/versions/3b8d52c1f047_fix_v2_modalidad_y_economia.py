"""FIX V2 de Fase 1: modalidad, elegibilidad, economía bottom-up y moneda por jurisdicción

Revision ID: 3b8d52c1f047
Revises: 2a7c41b0e9d2
Create Date: 2026-10-21

Tres cambios, todos auditables y sin borrar historia:

1. **La moneda deja de ser un ajuste global.** `universes.currency` y
   `clubs.currency` pasan a admitir nulo: la moneda de una institución sale del
   ancla monetaria de su territorio, y un universo ya no nace en pesos
   mexicanos por el idioma de la interfaz.
2. **Los clubes guardan lo que el generador decidió por ellos**: su forma de
   gobierno, su acuerdo de sede y el reparto de responsabilidades
   (`organization`), y el desglose de sus cuentas con el origen y la base de
   cada importe (`finance_profile`).
3. **Los reglamentos guardados se migran al schema 2.0.0**: desaparecen
   `generation.professionalization`, `generation.economy` y
   `generation.institutional_maturity` —los selectores de riqueza que el FIX V2
   prohíbe— y aparece `participation_modality`, que son reglas de participación.
   La equivalencia se registra en `rules_json.migration_note` para que quede
   constancia de qué se cambió y por qué, en vez de reescribir en silencio.
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision = '3b8d52c1f047'
down_revision = '2a7c41b0e9d2'
branch_labels = None
depends_on = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql')

#: Equivalencia del selector de riqueza eliminado a una modalidad de
#: participación. Donde el usuario no había declarado nada (`contextual_auto`)
#: se usa el alcance territorial como mejor aproximación disponible, y se dice.
_MODALITY_BY_LEVEL = {
    'amateur': 'amateur_organized',
    'semi_professional': 'semi_professional',
    'professional': 'professional',
    'elite': 'professional',
}
_MODALITY_BY_SCOPE = {
    'municipal': 'amateur_organized',
    'regional': 'amateur_organized',
    'national': 'semi_professional',
    'multinational': 'semi_professional',
}


def upgrade() -> None:
    with op.batch_alter_table('universes') as batch:
        batch.alter_column('currency', existing_type=sa.String(length=8), nullable=True)

    # El ancla monetaria viaja con la geografía del universo: sin ella, los
    # clubes no pueden tener importes y el presupuesto queda sin determinar.
    with op.batch_alter_table('places') as batch:
        batch.add_column(sa.Column('economy', JSON_TYPE, nullable=True))

    with op.batch_alter_table('clubs') as batch:
        batch.alter_column('currency', existing_type=sa.String(length=8), nullable=True)
        batch.add_column(
            sa.Column('organization', JSON_TYPE, nullable=False, server_default='{}')
        )
        batch.add_column(
            sa.Column('finance_profile', JSON_TYPE, nullable=False, server_default='{}')
        )

    _migrate_rulesets()


def _migrate_rulesets() -> None:
    """Reescribe los reglamentos guardados al schema 2.0.0, dejando constancia."""
    connection = op.get_bind()
    filas = connection.execute(
        sa.text('SELECT id, rules_json, schema_version FROM competition_rule_versions')
    ).fetchall()

    for fila in filas:
        crudo = fila[1]
        rules = json.loads(crudo) if isinstance(crudo, str) else dict(crudo)
        generation = dict(rules.get('generation') or {})

        nivel = generation.pop('professionalization', None)
        economia = generation.pop('economy', None)
        madurez = generation.pop('institutional_maturity', None)
        if nivel in (None, 'contextual_auto'):
            scope_level = (rules.get('scope') or {}).get('level', 'municipal')
            modalidad = _MODALITY_BY_SCOPE.get(scope_level, 'amateur_organized')
            motivo = (
                f'no había modalidad declarada (professionalization={nivel!r}); se usa '
                f'el alcance «{scope_level}» como aproximación'
            )
        else:
            modalidad = _MODALITY_BY_LEVEL.get(str(nivel), 'amateur_organized')
            motivo = f'professionalization={nivel!r} equivale a la modalidad «{modalidad}»'

        rules['generation'] = generation
        rules.setdefault('participation_modality', modalidad)
        rules['schema_version'] = '2.0.0'
        rules['migration_note'] = {
            'from_schema': fila[2],
            'reason': motivo,
            'removed_fields': {
                'professionalization': nivel,
                'economy': economia,
                'institutional_maturity': madurez,
            },
            'note': (
                'El FIX V2 de Fase 1 prohíbe que el formulario decida la riqueza de los '
                'clubes. Los importes de las temporadas ya jugadas NO se recalculan: '
                'quedan como se simularon.'
            ),
        }

        connection.execute(
            sa.text(
                'UPDATE competition_rule_versions '
                'SET rules_json = :rules, schema_version = :version WHERE id = :id'
            ),
            {'rules': json.dumps(rules, ensure_ascii=False), 'version': '2.0.0', 'id': fila[0]},
        )


def downgrade() -> None:
    # Volver atrás exige que la moneda deje de ser nula, y después de este fix
    # hay universos y clubes que legítimamente no la tienen —porque su
    # jurisdicción no la declara—. Se rellenan con el valor que el esquema
    # anterior daba por omisión, y queda dicho aquí que es una pérdida de
    # información: al revertir, un club ugandés pasará a figurar en pesos
    # mexicanos, que es precisamente el defecto que este fix corrigió.
    op.execute("UPDATE universes SET currency = 'MXN' WHERE currency IS NULL")
    op.execute("UPDATE clubs SET currency = 'MXN' WHERE currency IS NULL")

    with op.batch_alter_table('clubs') as batch:
        batch.drop_column('finance_profile')
        batch.drop_column('organization')
        batch.alter_column('currency', existing_type=sa.String(length=8), nullable=False)
    with op.batch_alter_table('places') as batch:
        batch.drop_column('economy')
    with op.batch_alter_table('universes') as batch:
        batch.alter_column('currency', existing_type=sa.String(length=8), nullable=False)
