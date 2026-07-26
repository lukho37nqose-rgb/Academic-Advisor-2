"""Add subject-initiated decision review cases.

Revision ID: e1b7d9a6c842
Revises: c9f2a7d4e615
Create Date: 2026-07-25 23:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e1b7d9a6c842'
down_revision: Union[str, Sequence[str], None] = 'c9f2a7d4e615'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'decision_review_cases',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('domain_id', sa.String(), nullable=False),
        sa.Column('subject_id', sa.String(), nullable=False),
        sa.Column('reasoning_graph_id', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('disputed_fact_paths', sa.JSON(), nullable=False),
        sa.Column('submitted_evidence_ids', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='SUBMITTED'),
        sa.Column('resolution', sa.String(), nullable=True),
        sa.Column('response_message', sa.Text(), nullable=True),
        sa.Column('response_due_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by', sa.String(), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('retention_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['reasoning_graph_id'], ['reasoning_graphs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_decision_review_cases_tenant_id', 'decision_review_cases', ['tenant_id'])
    op.create_index('ix_decision_review_cases_domain_id', 'decision_review_cases', ['domain_id'])
    op.create_index('ix_decision_review_cases_subject_id', 'decision_review_cases', ['subject_id'])
    op.create_index('ix_decision_review_cases_reasoning_graph_id', 'decision_review_cases', ['reasoning_graph_id'])
    op.create_index('ix_decision_review_cases_response_due_at', 'decision_review_cases', ['response_due_at'])
    op.create_index('ix_decision_review_cases_retention_expires_at', 'decision_review_cases', ['retention_expires_at'])

    op.create_table(
        'decision_review_case_events',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('review_case_id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('domain_id', sa.String(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('resolution', sa.String(), nullable=True),
        sa.Column('response_message', sa.Text(), nullable=True),
        sa.Column('actor_id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['review_case_id'], ['decision_review_cases.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('review_case_id', 'sequence', name='uq_decision_review_case_event_sequence'),
    )
    op.create_index('ix_decision_review_case_events_review_case_id', 'decision_review_case_events', ['review_case_id'])
    op.create_index('ix_decision_review_case_events_tenant_id', 'decision_review_case_events', ['tenant_id'])
    op.create_index('ix_decision_review_case_events_domain_id', 'decision_review_case_events', ['domain_id'])


def downgrade() -> None:
    op.drop_index('ix_decision_review_case_events_domain_id', table_name='decision_review_case_events')
    op.drop_index('ix_decision_review_case_events_tenant_id', table_name='decision_review_case_events')
    op.drop_index('ix_decision_review_case_events_review_case_id', table_name='decision_review_case_events')
    op.drop_table('decision_review_case_events')
    op.drop_index('ix_decision_review_cases_retention_expires_at', table_name='decision_review_cases')
    op.drop_index('ix_decision_review_cases_response_due_at', table_name='decision_review_cases')
    op.drop_index('ix_decision_review_cases_reasoning_graph_id', table_name='decision_review_cases')
    op.drop_index('ix_decision_review_cases_subject_id', table_name='decision_review_cases')
    op.drop_index('ix_decision_review_cases_domain_id', table_name='decision_review_cases')
    op.drop_index('ix_decision_review_cases_tenant_id', table_name='decision_review_cases')
    op.drop_table('decision_review_cases')
