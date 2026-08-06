"""Add reviewed source connector metadata.

Revision ID: 59d4c8e3a712
Revises: c1d4e8f2a617
"""

from alembic import op
import sqlalchemy as sa


revision = "59d4c8e3a712"
down_revision = "c1d4e8f2a617"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("institutional_data_sources", sa.Column("connector_kind", sa.String(), nullable=False, server_default="NONE"))
    op.add_column("institutional_data_sources", sa.Column("credential_reference", sa.String(), nullable=True))
    op.add_column("institutional_data_sources", sa.Column("endpoint_reference", sa.String(), nullable=True))
    op.add_column("institutional_data_sources", sa.Column("allowed_object", sa.String(), nullable=True))
    op.add_column("institutional_data_sources", sa.Column("connector_status", sa.String(), nullable=False, server_default="NOT_CONFIGURED"))
    op.add_column("institutional_data_sources", sa.Column("connector_last_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_institutional_data_source_connector_kind",
        "institutional_data_sources",
        "connector_kind IN ('NONE', 'REST_API', 'SFTP_PULL', 'DATABASE_VIEW', 'VENDOR_API')",
    )
    op.create_check_constraint(
        "ck_institutional_data_source_connector_status",
        "institutional_data_sources",
        "connector_status IN ('NOT_CONFIGURED', 'CONFIGURED', 'TEST_FAILED', 'APPROVED', 'PAUSED', 'RETIRED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_institutional_data_source_connector_status", "institutional_data_sources", type_="check")
    op.drop_constraint("ck_institutional_data_source_connector_kind", "institutional_data_sources", type_="check")
    op.drop_column("institutional_data_sources", "connector_last_checked_at")
    op.drop_column("institutional_data_sources", "connector_status")
    op.drop_column("institutional_data_sources", "allowed_object")
    op.drop_column("institutional_data_sources", "endpoint_reference")
    op.drop_column("institutional_data_sources", "credential_reference")
    op.drop_column("institutional_data_sources", "connector_kind")
