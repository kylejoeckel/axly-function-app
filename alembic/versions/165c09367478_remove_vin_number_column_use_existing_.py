"""Remove vin_number column, use existing vin column

Revision ID: 165c09367478
Revises: dd85e3bdb6df
Create Date: 2025-09-19 16:24:44.593327

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '165c09367478'
down_revision: Union[str, Sequence[str], None] = 'dd85e3bdb6df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Remove the newly added vin_number column, use existing vin column instead
    op.drop_column('vehicles', 'vin_number')


def downgrade() -> None:
    """Downgrade schema."""
    # Re-add the vin_number column if we need to rollback
    op.add_column('vehicles', sa.Column('vin_number', sa.Text(), nullable=True))
