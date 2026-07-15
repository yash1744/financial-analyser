"""add receipts and receipt_images

Revision ID: 20861e77bdce
Revises: 5a5c2c8f55ab
Create Date: 2026-07-15 03:38:22.602828

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = '20861e77bdce'
down_revision: str | None = '5a5c2c8f55ab'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'receipts',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('transaction_id', UUID(as_uuid=True), nullable=False),
        sa.Column('merchant_name', sa.String(length=255), nullable=True),
        sa.Column('receipt_date', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('tax_amount', sa.Numeric(19, 4), nullable=True),
        sa.Column('tip_amount', sa.Numeric(19, 4), nullable=True),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('transaction_id'),
    )
    op.create_table(
        'receipt_images',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('receipt_id', UUID(as_uuid=True), nullable=False),
        sa.Column('storage_key', sa.String(length=512), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['receipt_id'], ['receipts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('storage_key'),
    )
    op.create_index(
        op.f('ix_receipt_images_receipt_id'), 'receipt_images', ['receipt_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_receipt_images_receipt_id'), table_name='receipt_images')
    op.drop_table('receipt_images')
    op.drop_table('receipts')
