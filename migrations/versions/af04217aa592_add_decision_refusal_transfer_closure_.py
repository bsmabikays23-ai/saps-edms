"""Add decision, refusal, transfer, closure, and opening ground fields

Revision ID: af04217aa592
Revises: 26a787a7fa7c
Create Date: 2026-09-30
"""
from alembic import op
import sqlalchemy as sa


revision = 'af04217aa592'
down_revision = '26a787a7fa7c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('cases', schema=None) as batch_op:
        batch_op.add_column(sa.Column('incident_station', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('ground_sworn_statement', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('ground_officer_present', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('ground_court_order', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('sworn_statement_ref', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('decision', sa.String(length=20), nullable=False, server_default='Pending'))
        batch_op.add_column(sa.Column('decision_reason', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('decision_note', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('decision_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('decision_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('transfer_station', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('closure_reason', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('closure_reference', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('closure_note', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('closed_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('closed_at', sa.DateTime(), nullable=True))
        batch_op.create_foreign_key(
            'fk_cases_decision_by_id_users',
            'users', ['decision_by_id'], ['id'],
        )
        batch_op.create_foreign_key(
            'fk_cases_closed_by_id_users',
            'users', ['closed_by_id'], ['id'],
        )


def downgrade():
    with op.batch_alter_table('cases', schema=None) as batch_op:
        batch_op.drop_constraint('fk_cases_closed_by_id_users', type_='foreignkey')
        batch_op.drop_constraint('fk_cases_decision_by_id_users', type_='foreignkey')
        batch_op.drop_column('closed_at')
        batch_op.drop_column('closed_by_id')
        batch_op.drop_column('closure_note')
        batch_op.drop_column('closure_reference')
        batch_op.drop_column('closure_reason')
        batch_op.drop_column('transfer_station')
        batch_op.drop_column('decision_at')
        batch_op.drop_column('decision_by_id')
        batch_op.drop_column('decision_note')
        batch_op.drop_column('decision_reason')
        batch_op.drop_column('decision')
        batch_op.drop_column('sworn_statement_ref')
        batch_op.drop_column('ground_court_order')
        batch_op.drop_column('ground_officer_present')
        batch_op.drop_column('ground_sworn_statement')
        batch_op.drop_column('incident_station')