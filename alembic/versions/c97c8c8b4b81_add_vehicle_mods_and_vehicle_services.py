# alembic/versions/c97c8c8b4b81_add_vehicle_mods_and_vehicle_services.py
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "c97c8c8b4b81"
down_revision = "2123b4ab9cdc"  # or your merge id if you merged heads
branch_labels = None
depends_on = None


def upgrade():
    # no CREATE EXTENSION calls (blocked on Azure)

    op.create_table(
        "mods_library",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("category", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "vehicle_mods",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("vehicle_id", pg.UUID(as_uuid=True), sa.ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mod_library_id", pg.UUID(as_uuid=True), sa.ForeignKey("mods_library.id"), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("installed_on", sa.Date()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "mod_documents",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("mod_id", pg.UUID(as_uuid=True), sa.ForeignKey("vehicle_mods.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("file_type", sa.Text()),
        sa.Column("label", sa.Text()),
        sa.Column("uploaded_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )




def downgrade():
    op.drop_index("ix_service_reminders_vehicle_active", table_name="service_reminders")
    op.drop_index("ix_service_documents_service", table_name="service_documents")
    op.drop_index("ix_vehicle_services_vehicle_date", table_name="vehicle_services")

    op.drop_table("service_reminders")
    op.drop_table("service_documents")
    op.drop_table("vehicle_services")
    op.drop_table("services_library")
    op.drop_table("mod_documents")
    op.drop_table("vehicle_mods")
    op.drop_table("mods_library")
