"""Add durable group routing and escalation deadlines to casework.

Revision ID: d5e1a4b8c923
Revises: c1d4e8f2a617
"""

from alembic import op
import sqlalchemy as sa

revision = "d5e1a4b8c923"
down_revision = "c1d4e8f2a617"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("support_requests", "decision_review_cases"):
        op.add_column(table, sa.Column("responsible_group", sa.String(), nullable=True))
        op.add_column(table, sa.Column("fallback_group", sa.String(), nullable=True))
        op.add_column(table, sa.Column("escalation_due_at", sa.DateTime(timezone=True), nullable=True))
        op.create_index(f"ix_{table}_escalation_due_at", table, ["escalation_due_at"])


def downgrade() -> None:
    for table in ("decision_review_cases", "support_requests"):
        op.drop_index(f"ix_{table}_escalation_due_at", table_name=table)
        op.drop_column(table, "escalation_due_at")
        op.drop_column(table, "fallback_group")
        op.drop_column(table, "responsible_group")
