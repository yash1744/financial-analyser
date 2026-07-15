"""add account nickname

Revision ID: 055f10e82e18
Revises: 5a5c2c8f55ab
Create Date: 2026-07-15 03:53:54.398185

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '055f10e82e18'
down_revision: str | None = '20861e77bdce'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('accounts', sa.Column('nickname', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('accounts', 'nickname')
