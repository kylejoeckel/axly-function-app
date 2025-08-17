"""create vehicle_images table

Revision ID: 66e1a22892d7
Revises: f8ad74cf588d
Create Date: 2025-08-08 14:59:47.065974
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

# revision identifiers, used by Alembic.
revision = "66e1a22892d7"
down_revision = "2123b4ab9cdc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vehicle_images",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "vehicle_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("blob_name", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text()),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("bytes", sa.Integer()),
        sa.Column(
            "is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_vehicle_images_vehicle_id", "vehicle_images", ["vehicle_id"]
    )
    op.create_index(
        "ix_vehicle_images_created_at", "vehicle_images", ["created_at"]
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_vehicle_images_primary_per_vehicle "
        "ON vehicle_images(vehicle_id) WHERE is_primary = true"
    )


def downgrade() -> None:
    op.drop_index(
        "ux_vehicle_images_primary_per_vehicle", table_name="vehicle_images"
    )
    op.drop_index("ix_vehicle_images_created_at", table_name="vehicle_images")
    op.drop_index("ix_vehicle_images_vehicle_id", table_name="vehicle_images")
    op.drop_table("vehicle_images")
