"""empty message

Revision ID: fa097c276453
Revises: 66e1a22892d7
Create Date: 2025-08-08 21:02:23.898817
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fa097c276453"
down_revision: Union[str, Sequence[str], None] = "66e1a22892d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("vehicles", sa.Column("submodel", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("vehicles", "submodel")
