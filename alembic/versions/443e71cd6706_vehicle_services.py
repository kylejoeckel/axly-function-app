"""add vehicle services, documents, and reminders

Revision ID: 443e71cd6706
Revises: fa097c276453
Create Date: 2025-08-09 10:49:08.060373
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '443e71cd6706'
down_revision: Union[str, Sequence[str], None] = 'fa097c276453'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add services, service documents, and service reminders."""
    # services_library
    op.create_table(
        'services_library',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('category', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('default_interval_miles', sa.Integer(), nullable=True),
        sa.Column('default_interval_months', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.UniqueConstraint('name', name='uq_services_library_name'),
    )

    # vehicle_services
    op.create_table(
        'vehicle_services',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('vehicle_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('vehicles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('service_library_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('services_library.id'), nullable=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('performed_on', sa.Date(), nullable=True),
        sa.Column('odometer_miles', sa.Integer(), nullable=True),
        sa.Column('cost_cents', sa.Integer(), nullable=True),
        sa.Column('currency', sa.Text(), server_default=sa.text("'USD'"), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
    )

    # service_documents
    op.create_table(
        'service_documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('service_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('vehicle_services.id', ondelete='CASCADE'), nullable=False),
        sa.Column('file_url', sa.Text(), nullable=False),
        sa.Column('file_type', sa.Text(), nullable=True),
        sa.Column('label', sa.Text(), nullable=True),
        sa.Column('uploaded_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
    )

    # service_reminders
    op.create_table(
        'service_reminders',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('vehicle_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('vehicles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('service_library_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('services_library.id'), nullable=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),

        sa.Column('interval_miles', sa.Integer(), nullable=True),
        sa.Column('interval_months', sa.Integer(), nullable=True),

        sa.Column('last_performed_on', sa.Date(), nullable=True),
        sa.Column('last_odometer', sa.Integer(), nullable=True),

        sa.Column('next_due_on', sa.Date(), nullable=True),
        sa.Column('next_due_miles', sa.Integer(), nullable=True),

        sa.Column('remind_ahead_miles', sa.Integer(), server_default=sa.text('0'), nullable=True),
        sa.Column('remind_ahead_days', sa.Integer(), server_default=sa.text('0'), nullable=True),

        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('last_notified_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),

        sa.CheckConstraint(
            'interval_miles IS NOT NULL OR interval_months IS NOT NULL',
            name='service_reminders_interval_nonnull'
        ),
    )

    # indexes
    op.create_index(
        'ix_vehicle_services_vehicle_date',
        'vehicle_services', ['vehicle_id', 'performed_on'], unique=False
    )
    op.create_index(
        'ix_service_documents_service',
        'service_documents', ['service_id'], unique=False
    )
    op.create_index(
        'ix_service_reminders_vehicle_active',
        'service_reminders', ['vehicle_id', 'is_active'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema: drop reminders, documents, services, and library."""
    # drop indexes first (some backends require this before dropping tables)
    op.drop_index('ix_service_reminders_vehicle_active', table_name='service_reminders')
    op.drop_index('ix_service_documents_service', table_name='service_documents')
    op.drop_index('ix_vehicle_services_vehicle_date', table_name='vehicle_services')

    # drop tables in reverse dependency order
    op.drop_table('service_reminders')
    op.drop_table('service_documents')
    op.drop_table('vehicle_services')
    op.drop_table('services_library')
