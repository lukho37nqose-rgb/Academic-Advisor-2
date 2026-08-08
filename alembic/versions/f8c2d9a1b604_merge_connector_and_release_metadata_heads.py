"""Merge connector metadata and release approval metadata heads.

Revision ID: f8c2d9a1b604
Revises: 59d4c8e3a712, b2f5d0e1c4aa
Create Date: 2026-08-08 00:00:00.000000
"""

from typing import Sequence, Union


revision: str = "f8c2d9a1b604"
down_revision: Union[str, Sequence[str], None] = ("59d4c8e3a712", "b2f5d0e1c4aa")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
