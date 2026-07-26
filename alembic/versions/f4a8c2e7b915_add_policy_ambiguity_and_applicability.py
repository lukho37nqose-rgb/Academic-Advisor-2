"""Add governed policy ambiguities and release applicability controls.

Revision ID: f4a8c2e7b915
Revises: e1b7d9a6c842
Create Date: 2026-07-26 00:15:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4a8c2e7b915"
down_revision: Union[str, Sequence[str], None] = "e1b7d9a6c842"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("releases", sa.Column("effective_from", sa.Date(), nullable=True))
    op.add_column("releases", sa.Column("effective_until", sa.Date(), nullable=True))
    op.add_column("releases", sa.Column("applicability", sa.JSON(), nullable=True))

    op.create_table(
        "policy_ambiguities",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("domain_id", sa.String(), nullable=False),
        sa.Column("source_citation", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("interpretation_options", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="OPEN"),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("resolution_source_reference", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.String(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["domain_id"], ["domains.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_policy_ambiguities_tenant_id", "policy_ambiguities", ["tenant_id"])
    op.create_index("ix_policy_ambiguities_domain_id", "policy_ambiguities", ["domain_id"])
    op.create_index("ix_policy_ambiguities_status", "policy_ambiguities", ["status"])

    op.create_table(
        "policy_ambiguity_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("ambiguity_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("domain_id", sa.String(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("source_reference", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["ambiguity_id"], ["policy_ambiguities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ambiguity_id", "sequence", name="uq_policy_ambiguity_event_sequence"),
    )
    op.create_index("ix_policy_ambiguity_events_ambiguity_id", "policy_ambiguity_events", ["ambiguity_id"])
    op.create_index("ix_policy_ambiguity_events_tenant_id", "policy_ambiguity_events", ["tenant_id"])
    op.create_index("ix_policy_ambiguity_events_domain_id", "policy_ambiguity_events", ["domain_id"])


def downgrade() -> None:
    op.drop_index("ix_policy_ambiguity_events_domain_id", table_name="policy_ambiguity_events")
    op.drop_index("ix_policy_ambiguity_events_tenant_id", table_name="policy_ambiguity_events")
    op.drop_index("ix_policy_ambiguity_events_ambiguity_id", table_name="policy_ambiguity_events")
    op.drop_table("policy_ambiguity_events")
    op.drop_index("ix_policy_ambiguities_status", table_name="policy_ambiguities")
    op.drop_index("ix_policy_ambiguities_domain_id", table_name="policy_ambiguities")
    op.drop_index("ix_policy_ambiguities_tenant_id", table_name="policy_ambiguities")
    op.drop_table("policy_ambiguities")
    op.drop_column("releases", "applicability")
    op.drop_column("releases", "effective_until")
    op.drop_column("releases", "effective_from")
