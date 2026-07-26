"""Add JSONB dynamic typing for Postgres

Revision ID: 0e32ea87a662
Revises: 7f052dfd730e
Create Date: 2026-07-24 19:49:16.204175

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0e32ea87a662'
down_revision: Union[str, Sequence[str], None] = '7f052dfd730e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to use JSONB dynamically where applicable."""
    conn = op.get_bind()
    
    if conn.dialect.name == 'postgresql':
        op.execute('ALTER TABLE domains ALTER COLUMN schema_definition TYPE JSONB USING schema_definition::jsonb')
        op.execute('ALTER TABLE rule_graphs ALTER COLUMN compiled_bytecode TYPE JSONB USING compiled_bytecode::jsonb')
        op.execute('ALTER TABLE reasoning_graphs ALTER COLUMN graph_data TYPE JSONB USING graph_data::jsonb')


def downgrade() -> None:
    """Downgrade schema back to JSON."""
    conn = op.get_bind()
    
    if conn.dialect.name == 'postgresql':
        op.execute('ALTER TABLE domains ALTER COLUMN schema_definition TYPE JSON USING schema_definition::json')
        op.execute('ALTER TABLE rule_graphs ALTER COLUMN compiled_bytecode TYPE JSON USING compiled_bytecode::json')
        op.execute('ALTER TABLE reasoning_graphs ALTER COLUMN graph_data TYPE JSON USING graph_data::json')
