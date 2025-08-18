"""merge all heads before mods/services

Revision ID: b429c19a8777
Revises: 443e71cd6706, c97c8c8b4b81
Create Date: 2025-08-18 10:13:33.368994

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b429c19a8777'
down_revision: Union[str, Sequence[str], None] = ('443e71cd6706', 'c97c8c8b4b81')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
