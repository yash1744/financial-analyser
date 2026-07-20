"""add user categories and category mappings

Revision ID: c69636b440f4
Revises: 1c451c363bfb
Create Date: 2026-07-20 01:35:07.553696

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = 'c69636b440f4'
down_revision: str | None = '1c451c363bfb'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'user_categories',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'name'),
    )
    op.create_index(op.f('ix_user_categories_user_id'), 'user_categories', ['user_id'], unique=False)
    op.create_table(
        'category_mappings',
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('category_id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_category_id', UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_category_id'], ['user_categories.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'category_id'),
    )
    op.create_index(op.f('ix_category_mappings_user_category_id'), 'category_mappings', ['user_category_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_category_mappings_user_category_id'), table_name='category_mappings')
    op.drop_table('category_mappings')
    op.drop_index(op.f('ix_user_categories_user_id'), table_name='user_categories')
    op.drop_table('user_categories')
