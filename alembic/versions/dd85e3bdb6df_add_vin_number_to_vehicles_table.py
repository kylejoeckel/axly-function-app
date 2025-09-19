"""Add vin_number to vehicles table

Revision ID: dd85e3bdb6df
Revises: 15ce273a5e70
Create Date: 2025-09-19 16:02:21.825385

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dd85e3bdb6df'
down_revision: Union[str, Sequence[str], None] = '15ce273a5e70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add vin_number column to vehicles table
    op.add_column('vehicles', sa.Column('vin_number', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove vin_number column from vehicles table
    op.drop_column('vehicles', 'vin_number')
