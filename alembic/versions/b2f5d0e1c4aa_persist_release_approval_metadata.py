"""Persist release approval metadata on policy drafts.

Revision ID: b2f5d0e1c4aa
Revises: f0d9c6a2b581
Create Date: 2026-08-04 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2f5d0e1c4aa"
down_revision: Union[str, Sequence[str], None] = "f0d9c6a2b581"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("policy_drafts", sa.Column("approved_by", sa.String(), nullable=True))
    op.add_column("policy_drafts", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("policy_drafts", "approved_at")
    op.drop_column("policy_drafts", "approved_by")
