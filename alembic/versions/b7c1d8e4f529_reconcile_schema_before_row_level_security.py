"""Reconcile ORM schema declarations before enabling PostgreSQL RLS.

Revision ID: b7c1d8e4f529
Revises: b6e3d1a9f824
Create Date: 2026-07-26 03:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c1d8e4f529"
down_revision: Union[str, Sequence[str], None] = "b6e3d1a9f824"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the governed-draft store and complete missing trace references."""
    op.create_table(
        "policy_drafts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("domain_id", sa.String(), nullable=False),
        sa.Column("policy_name", sa.String(), nullable=False),
        sa.Column("author_id", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("released_as_release_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["domain_id"], ["domains.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # PostgreSQL received these in c4d8f2a7e913. SQLite needs batch mode to
    # recreate the table with them, keeping schema audits consistent in CI.
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("reasoning_graphs", recreate="always") as batch:
            batch.create_foreign_key(
                "fk_reasoning_graphs_release_id",
                "releases",
                ["release_id"],
                ["id"],
            )
            batch.create_foreign_key(
                "fk_reasoning_graphs_evidence_id",
                "evidence",
                ["evidence_id"],
                ["id"],
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("reasoning_graphs", recreate="always") as batch:
            batch.drop_constraint("fk_reasoning_graphs_evidence_id", type_="foreignkey")
            batch.drop_constraint("fk_reasoning_graphs_release_id", type_="foreignkey")
    op.drop_table("policy_drafts")
