"""add idempotency fields for system record imports

Revision ID: e1a6c8f93d24
Revises: d7f4b8e29a61
"""

from alembic import op
import sqlalchemy as sa


revision = "e1a6c8f93d24"
down_revision = "d7f4b8e29a61"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("evidence") as batch_op:
        batch_op.add_column(sa.Column("source_mapping_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("source_record_fingerprint", sa.String(), nullable=True))
        batch_op.create_unique_constraint(
            "uq_evidence_source_record_fingerprint",
            ["tenant_id", "domain_id", "source_mapping_id", "source_record_fingerprint"],
        )


def downgrade() -> None:
    with op.batch_alter_table("evidence") as batch_op:
        batch_op.drop_constraint("uq_evidence_source_record_fingerprint", type_="unique")
        batch_op.drop_column("source_record_fingerprint")
        batch_op.drop_column("source_mapping_id")
