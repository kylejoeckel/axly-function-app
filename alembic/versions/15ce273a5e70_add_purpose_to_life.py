"""empty message

Revision ID: 15ce273a5e70
Revises: b429c19a8777
Create Date: 2025-08-24 08:03:10.237551

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '15ce273a5e70'
down_revision: Union[str, Sequence[str], None] = 'b429c19a8777'
branch_labels = None
depends_on = None

def upgrade():
    # 1) Add column as nullable with a server_default to backfill quickly/safely
    op.add_column(
        "email_verifications",
        sa.Column("purpose", sa.String(length=32), nullable=True, server_default="signup"),
    )

    # 2) Ensure existing rows are populated (defensive — some PG versions won’t rewrite old rows)
    op.execute("UPDATE email_verifications SET purpose = 'signup' WHERE purpose IS NULL")

    # 3) Make it NOT NULL; optionally drop the server default if you prefer app-level defaults
    op.alter_column(
        "email_verifications",
        "purpose",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default=None,  # keep None if you want to control default in app code
    )

    # 4) Index to match query pattern: email + purpose + pin
    op.create_index(
        "ix_email_verifications_email_purpose_pin",
        "email_verifications",
        ["email", "purpose", "pin"],
        unique=False,
    )

def downgrade():
    op.drop_index("ix_email_verifications_email_purpose_pin", table_name="email_verifications")
    op.drop_column("email_verifications", "purpose")