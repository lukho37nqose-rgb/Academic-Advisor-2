"""Add Tier 1 governance tables

Revision ID: a19d8c2f4b61
Revises: 0e32ea87a662
Create Date: 2026-07-25 12:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a19d8c2f4b61'
down_revision: Union[str, Sequence[str], None] = '0e32ea87a662'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add append-only quick-edit audit and current metadata override tables."""
    op.create_table(
        'metadata_overrides',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('domain_id', sa.String(), nullable=False),
        sa.Column('target_type', sa.String(), nullable=False),
        sa.Column('target_id', sa.String(), nullable=False),
        sa.Column('field_name', sa.String(), nullable=False),
        sa.Column('current_value', sa.Text(), nullable=False),
        sa.Column('updated_by', sa.String(), nullable=False),
        sa.Column('last_edit_id', sa.String(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'tenant_id',
            'domain_id',
            'target_type',
            'target_id',
            'field_name',
            name='uq_metadata_override_target_field',
        ),
    )
    op.create_index(
        'ix_metadata_overrides_lookup',
        'metadata_overrides',
        ['tenant_id', 'domain_id', 'target_type', 'target_id'],
    )

    op.create_table(
        'metadata_quick_edits',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('domain_id', sa.String(), nullable=False),
        sa.Column('target_type', sa.String(), nullable=False),
        sa.Column('target_id', sa.String(), nullable=False),
        sa.Column('field_name', sa.String(), nullable=False),
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('source_reference', sa.String(), nullable=True),
        sa.Column('actor_id', sa.String(), nullable=False),
        sa.Column('actor_role', sa.String(), nullable=False),
        sa.Column('applied_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_metadata_quick_edits_tenant_domain',
        'metadata_quick_edits',
        ['tenant_id', 'domain_id'],
    )


def downgrade() -> None:
    """Remove Tier 1 governance tables."""
    op.drop_index('ix_metadata_quick_edits_tenant_domain', table_name='metadata_quick_edits')
    op.drop_table('metadata_quick_edits')
    op.drop_index('ix_metadata_overrides_lookup', table_name='metadata_overrides')
    op.drop_table('metadata_overrides')
