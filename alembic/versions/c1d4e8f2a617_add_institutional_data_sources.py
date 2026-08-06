"""Add governed institutional data-source declarations.

Revision ID: c1d4e8f2a617
Revises: b9e5a6c7d821
"""

from alembic import op
import sqlalchemy as sa


revision = "c1d4e8f2a617"
down_revision = "b9e5a6c7d821"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "institutional_data_sources",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("domain_id", sa.String(), sa.ForeignKey("domains.id"), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("source_kind", sa.String(), nullable=False),
        sa.Column("authority_level", sa.String(), nullable=False),
        sa.Column("source_owner", sa.String(), nullable=False),
        sa.Column("expected_refresh_hours", sa.Integer(), nullable=True),
        sa.Column("source_reference", sa.String(), nullable=True),
        sa.Column("author_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("reviewed_by", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_institutional_data_sources_tenant_domain", "institutional_data_sources", ["tenant_id", "domain_id"])
    op.add_column("system_record_import_mappings", sa.Column("source_id", sa.String(), nullable=True))
    op.create_index("ix_system_record_import_mappings_source_id", "system_record_import_mappings", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_system_record_import_mappings_source_id", table_name="system_record_import_mappings")
    op.drop_column("system_record_import_mappings", "source_id")
    op.drop_index("ix_institutional_data_sources_tenant_domain", table_name="institutional_data_sources")
    op.drop_table("institutional_data_sources")
