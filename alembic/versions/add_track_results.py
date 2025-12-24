"""Add track_results table for performance timing

Revision ID: add_track_001
Revises: add_products_001
Create Date: 2025-12-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_track_001'
down_revision: Union[str, Sequence[str], None] = 'add_products_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create track_results table."""
    op.create_table(
        'track_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('vehicle_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('vehicles.id', ondelete='CASCADE'), nullable=False),

        # Race configuration
        sa.Column('race_type', sa.Text(), nullable=False),
        sa.Column('tree_type', sa.Text(), nullable=False),

        # Timing data (stored in milliseconds)
        sa.Column('elapsed_time', sa.Integer(), nullable=False),
        sa.Column('reaction_time', sa.Integer(), nullable=True),
        sa.Column('trap_speed', sa.Float(), nullable=True),
        sa.Column('distance_traveled', sa.Float(), nullable=True),
        sa.Column('is_false_start', sa.Boolean(), server_default=sa.text('false'), nullable=False),

        # Splits (stored as JSON array)
        sa.Column('splits', postgresql.JSON(), nullable=True),

        # Conditions (optional)
        sa.Column('temperature', sa.Float(), nullable=True),
        sa.Column('humidity', sa.Float(), nullable=True),
        sa.Column('altitude', sa.Integer(), nullable=True),

        # Location (optional)
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('location_name', sa.Text(), nullable=True),

        # Metadata
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
    )

    # Create indexes for common queries
    op.create_index('idx_track_results_user_id', 'track_results', ['user_id'])
    op.create_index('idx_track_results_vehicle_id', 'track_results', ['vehicle_id'])
    op.create_index('idx_track_results_vehicle_race_type', 'track_results', ['vehicle_id', 'race_type'])


def downgrade() -> None:
    """Drop track_results table."""
    op.drop_index('idx_track_results_vehicle_race_type', 'track_results')
    op.drop_index('idx_track_results_vehicle_id', 'track_results')
    op.drop_index('idx_track_results_user_id', 'track_results')
    op.drop_table('track_results')
