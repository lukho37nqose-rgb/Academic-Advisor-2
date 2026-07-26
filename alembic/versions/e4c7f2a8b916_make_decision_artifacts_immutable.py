"""Make decision-bearing records append-only in PostgreSQL.

Revision ID: e4c7f2a8b916
Revises: b4e6f1a9d205
Create Date: 2026-07-26 21:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "e4c7f2a8b916"
down_revision: Union[str, Sequence[str], None] = "b4e6f1a9d205"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_IMMUTABLE_TABLES = (
    "evidence",
    "claims",
    "facts",
    "reasoning_graphs",
    "releases",
    "rule_graphs",
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
        CREATE OR REPLACE FUNCTION ire.prevent_decision_artifact_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'Decision-bearing records are append-only; create a governed successor instead';
        END;
        $$
    """)
    for table_name in _IMMUTABLE_TABLES:
        trigger_name = f"prevent_{table_name}_mutation"
        op.execute(
            f"CREATE TRIGGER {trigger_name} BEFORE UPDATE OR DELETE ON {table_name} "
            "FOR EACH ROW EXECUTE FUNCTION ire.prevent_decision_artifact_mutation()"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table_name in _IMMUTABLE_TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS prevent_{table_name}_mutation ON {table_name}")
        op.execute("DROP FUNCTION IF EXISTS ire.prevent_decision_artifact_mutation()")
