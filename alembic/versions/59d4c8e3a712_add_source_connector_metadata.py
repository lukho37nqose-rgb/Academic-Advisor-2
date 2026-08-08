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
    with op.batch_alter_table("institutional_data_sources") as batch_op:
        batch_op.add_column(sa.Column("connector_kind", sa.String(), nullable=False, server_default="NONE"))
        batch_op.add_column(sa.Column("credential_reference", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("endpoint_reference", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("allowed_object", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("connector_status", sa.String(), nullable=False, server_default="NOT_CONFIGURED"))
        batch_op.add_column(sa.Column("connector_last_checked_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_check_constraint(
            "ck_institutional_data_source_connector_kind",
            "connector_kind IN ('NONE', 'REST_API', 'SFTP_PULL', 'DATABASE_VIEW', 'VENDOR_API')",
        )
        batch_op.create_check_constraint(
            "ck_institutional_data_source_connector_status",
            "connector_status IN ('NOT_CONFIGURED', 'CONFIGURED', 'TEST_FAILED', 'APPROVED', 'PAUSED', 'RETIRED')",
        )


def downgrade() -> None:
    with op.batch_alter_table("institutional_data_sources") as batch_op:
        batch_op.drop_constraint("ck_institutional_data_source_connector_status", type_="check")
        batch_op.drop_constraint("ck_institutional_data_source_connector_kind", type_="check")
        batch_op.drop_column("connector_last_checked_at")
        batch_op.drop_column("connector_status")
        batch_op.drop_column("allowed_object")
        batch_op.drop_column("endpoint_reference")
        batch_op.drop_column("credential_reference")
        batch_op.drop_column("connector_kind")
