"""add_pid_tables

Revision ID: 7b87eef423eb
Revises: add_track_001
Create Date: 2025-12-27 15:58:44.598488

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '7b87eef423eb'
down_revision: Union[str, Sequence[str], None] = 'add_track_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('discovered_pids',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('vin', sa.Text(), nullable=False),
    sa.Column('vin_prefix', sa.Text(), nullable=False),
    sa.Column('manufacturer', sa.Enum('VAG', 'BMW', 'TOYOTA', 'GM', 'FORD', 'STELLANTIS', 'HONDA', 'NISSAN', 'HYUNDAI', 'MERCEDES', 'GENERIC', name='manufacturergroup'), nullable=False),
    sa.Column('pid_id', sa.Text(), nullable=False),
    sa.Column('success', sa.Boolean(), nullable=False),
    sa.Column('response_time_ms', sa.Integer(), nullable=True),
    sa.Column('raw_response', sa.Text(), nullable=True),
    sa.Column('device_type', sa.Text(), nullable=True),
    sa.Column('reported_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_discovered_pids_manufacturer', 'discovered_pids', ['manufacturer'], unique=False)
    op.create_index('ix_discovered_pids_pid_id_success', 'discovered_pids', ['pid_id', 'success'], unique=False)
    op.create_index('ix_discovered_pids_vin_prefix', 'discovered_pids', ['vin_prefix'], unique=False)
    op.create_index('ix_discovered_pids_vin_prefix_pid', 'discovered_pids', ['vin_prefix', 'pid_id'], unique=False)
    op.create_table('pid_profiles',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('vin_prefix', sa.Text(), nullable=False),
    sa.Column('manufacturer', sa.Enum('VAG', 'BMW', 'TOYOTA', 'GM', 'FORD', 'STELLANTIS', 'HONDA', 'NISSAN', 'HYUNDAI', 'MERCEDES', 'GENERIC', name='manufacturergroup'), nullable=False),
    sa.Column('platform', sa.Text(), nullable=True),
    sa.Column('boost_pid', sa.Text(), nullable=True),
    sa.Column('oil_temp_pid', sa.Text(), nullable=True),
    sa.Column('charge_air_temp_pid', sa.Text(), nullable=True),
    sa.Column('trans_temp_pid', sa.Text(), nullable=True),
    sa.Column('working_pids', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('failed_pids', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('sample_count', sa.Integer(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('vin_prefix')
    )
    op.create_index('ix_pid_profiles_manufacturer', 'pid_profiles', ['manufacturer'], unique=False)
    op.create_table('pid_registry',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('pid_id', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('manufacturer', sa.Enum('VAG', 'BMW', 'TOYOTA', 'GM', 'FORD', 'STELLANTIS', 'HONDA', 'NISSAN', 'HYUNDAI', 'MERCEDES', 'GENERIC', name='manufacturergroup'), nullable=False),
    sa.Column('platform', sa.Text(), nullable=True),
    sa.Column('mode', sa.Text(), nullable=False),
    sa.Column('pid', sa.Text(), nullable=False),
    sa.Column('header', sa.Text(), nullable=True),
    sa.Column('formula', sa.Text(), nullable=False),
    sa.Column('unit', sa.Text(), nullable=False),
    sa.Column('min_value', sa.Float(), nullable=True),
    sa.Column('max_value', sa.Float(), nullable=True),
    sa.Column('bytes_count', sa.Integer(), nullable=False),
    sa.Column('category', sa.Enum('ENGINE', 'FUEL', 'ELECTRICAL', 'TRANSMISSION', 'CLIMATE', 'OTHER', name='pidcategory'), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('pid_id')
    )
    op.create_index('ix_pid_registry_category', 'pid_registry', ['category'], unique=False)
    op.create_index('ix_pid_registry_manufacturer', 'pid_registry', ['manufacturer'], unique=False)
    op.create_index('ix_pid_registry_manufacturer_category', 'pid_registry', ['manufacturer', 'category'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_pid_registry_manufacturer_category', table_name='pid_registry')
    op.drop_index('ix_pid_registry_manufacturer', table_name='pid_registry')
    op.drop_index('ix_pid_registry_category', table_name='pid_registry')
    op.drop_table('pid_registry')
    op.drop_index('ix_pid_profiles_manufacturer', table_name='pid_profiles')
    op.drop_table('pid_profiles')
    op.drop_index('ix_discovered_pids_vin_prefix_pid', table_name='discovered_pids')
    op.drop_index('ix_discovered_pids_vin_prefix', table_name='discovered_pids')
    op.drop_index('ix_discovered_pids_pid_id_success', table_name='discovered_pids')
    op.drop_index('ix_discovered_pids_manufacturer', table_name='discovered_pids')
    op.drop_table('discovered_pids')
    op.execute("DROP TYPE IF EXISTS manufacturergroup")
    op.execute("DROP TYPE IF EXISTS pidcategory")
