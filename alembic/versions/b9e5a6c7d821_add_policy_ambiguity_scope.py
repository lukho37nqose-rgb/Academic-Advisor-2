"""Scope policy ambiguities to the policy fields they affect.

Revision ID: b9e5a6c7d821
Revises: a6c3b2e91d75
"""

from alembic import op
import sqlalchemy as sa


revision = "b9e5a6c7d821"
down_revision = "a6c3b2e91d75"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("policy_ambiguities") as batch_op:
        batch_op.add_column(sa.Column("affected_target_paths", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("policy_ambiguities") as batch_op:
        batch_op.drop_column("affected_target_paths")
