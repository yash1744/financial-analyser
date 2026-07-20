"""add labels and transaction labels

Revision ID: 1c451c363bfb
Revises: 1349448d8fca
Create Date: 2026-07-19 10:24:42.619594

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = '1c451c363bfb'
down_revision: str | None = '1349448d8fca'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'labels',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'name'),
    )
    op.create_index(op.f('ix_labels_user_id'), 'labels', ['user_id'], unique=False)
    op.create_table(
        'transaction_labels',
        sa.Column('transaction_id', UUID(as_uuid=True), nullable=False),
        sa.Column('label_id', UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['label_id'], ['labels.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('transaction_id', 'label_id'),
    )


def downgrade() -> None:
    op.drop_table('transaction_labels')
    op.drop_index(op.f('ix_labels_user_id'), table_name='labels')
    op.drop_table('labels')
