"""Retain release verification bundles and support safe key rotation.

Revision ID: b6e3d1a9f824
Revises: f4a8c2e7b915
Create Date: 2026-07-26 01:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b6e3d1a9f824"
down_revision: Union[str, Sequence[str], None] = "f4a8c2e7b915"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("releases", sa.Column("signed_payload", sa.JSON(), nullable=True))
    op.add_column("releases", sa.Column("signed_payload_hash", sa.String(), nullable=True))
    op.add_column("releases", sa.Column("signing_key_id", sa.String(), nullable=True))
    op.add_column("releases", sa.Column("signing_public_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("releases", "signing_public_key")
    op.drop_column("releases", "signing_key_id")
    op.drop_column("releases", "signed_payload_hash")
    op.drop_column("releases", "signed_payload")
