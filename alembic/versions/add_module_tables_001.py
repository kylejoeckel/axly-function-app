"""add_module_tables

Revision ID: add_module_tables_001
Revises: 7b87eef423eb
Create Date: 2025-12-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'add_module_tables_001'
down_revision: Union[str, Sequence[str], None] = '7b87eef423eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Reference existing manufacturergroup enum (created in PID migration)
manufacturergroup_enum = postgresql.ENUM(
    'VAG', 'BMW', 'TOYOTA', 'GM', 'FORD', 'STELLANTIS', 'HONDA', 'NISSAN', 'HYUNDAI', 'MERCEDES', 'GENERIC',
    name='manufacturergroup',
    create_type=False
)

# New enums for this migration
codingcategory_enum = postgresql.ENUM(
    'comfort', 'lighting', 'display', 'safety', 'performance', 'audio', 'other',
    name='codingcategory',
    create_type=False
)

codingsafetylevel_enum = postgresql.ENUM(
    'safe', 'caution', 'advanced',
    name='codingsafetylevel',
    create_type=False
)


def upgrade() -> None:
    # Create new enums (manufacturergroup already exists from PID migration)
    op.execute("CREATE TYPE codingcategory AS ENUM ('comfort', 'lighting', 'display', 'safety', 'performance', 'audio', 'other')")
    op.execute("CREATE TYPE codingsafetylevel AS ENUM ('safe', 'caution', 'advanced')")

    # Create module_registry table
    op.create_table('module_registry',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('manufacturer', manufacturergroup_enum, nullable=False),
        sa.Column('address', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('long_name', sa.Text(), nullable=True),
        sa.Column('can_id', sa.Text(), nullable=False),
        sa.Column('can_id_response', sa.Text(), nullable=True),
        sa.Column('coding_supported', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('coding_did', sa.Text(), nullable=True, server_default='F19E'),
        sa.Column('coding_length', sa.Integer(), nullable=True),
        sa.Column('platforms', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('year_min', sa.Integer(), nullable=True),
        sa.Column('year_max', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_module_registry_manufacturer', 'module_registry', ['manufacturer'], unique=False)
    op.create_index('ix_module_registry_manufacturer_address', 'module_registry', ['manufacturer', 'address'], unique=True)
    op.create_index('ix_module_registry_platforms', 'module_registry', ['platforms'], unique=False, postgresql_using='gin')

    # Create coding_bit_registry table
    op.create_table('coding_bit_registry',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('manufacturer', manufacturergroup_enum, nullable=False),
        sa.Column('module_address', sa.Text(), nullable=False),
        sa.Column('byte_index', sa.Integer(), nullable=False),
        sa.Column('bit_index', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', codingcategory_enum, nullable=False, server_default='other'),
        sa.Column('safety_level', codingsafetylevel_enum, nullable=False, server_default='safe'),
        sa.Column('platforms', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('requires', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('conflicts', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('source', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_coding_bit_manufacturer', 'coding_bit_registry', ['manufacturer'], unique=False)
    op.create_index('ix_coding_bit_module', 'coding_bit_registry', ['manufacturer', 'module_address'], unique=False)
    op.create_index('ix_coding_bit_location', 'coding_bit_registry', ['manufacturer', 'module_address', 'byte_index', 'bit_index'], unique=True)
    op.create_index('ix_coding_bit_category', 'coding_bit_registry', ['category'], unique=False)

    # Create discovered_modules table
    op.create_table('discovered_modules',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('vin', sa.Text(), nullable=False),
        sa.Column('vin_prefix', sa.Text(), nullable=False),
        sa.Column('manufacturer', manufacturergroup_enum, nullable=False),
        sa.Column('module_address', sa.Text(), nullable=False),
        sa.Column('is_present', sa.Boolean(), nullable=False),
        sa.Column('part_number', sa.Text(), nullable=True),
        sa.Column('software_version', sa.Text(), nullable=True),
        sa.Column('hardware_version', sa.Text(), nullable=True),
        sa.Column('coding_value', sa.Text(), nullable=True),
        sa.Column('device_type', sa.Text(), nullable=True),
        sa.Column('reported_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_discovered_modules_vin_prefix', 'discovered_modules', ['vin_prefix'], unique=False)
    op.create_index('ix_discovered_modules_manufacturer', 'discovered_modules', ['manufacturer'], unique=False)
    op.create_index('ix_discovered_modules_module', 'discovered_modules', ['manufacturer', 'module_address'], unique=False)

    # Create coding_history table
    op.create_table('coding_history',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('vehicle_id', sa.UUID(), nullable=False),
        sa.Column('manufacturer', manufacturergroup_enum, nullable=False),
        sa.Column('module_address', sa.Text(), nullable=False),
        sa.Column('coding_before', sa.Text(), nullable=False),
        sa.Column('coding_after', sa.Text(), nullable=False),
        sa.Column('changes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('applied_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=True),
        sa.Column('reverted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('reverted_at', sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_coding_history_user', 'coding_history', ['user_id'], unique=False)
    op.create_index('ix_coding_history_vehicle', 'coding_history', ['vehicle_id'], unique=False)
    op.create_index('ix_coding_history_user_vehicle', 'coding_history', ['user_id', 'vehicle_id'], unique=False)


def downgrade() -> None:
    # Drop coding_history
    op.drop_index('ix_coding_history_user_vehicle', table_name='coding_history')
    op.drop_index('ix_coding_history_vehicle', table_name='coding_history')
    op.drop_index('ix_coding_history_user', table_name='coding_history')
    op.drop_table('coding_history')

    # Drop discovered_modules
    op.drop_index('ix_discovered_modules_module', table_name='discovered_modules')
    op.drop_index('ix_discovered_modules_manufacturer', table_name='discovered_modules')
    op.drop_index('ix_discovered_modules_vin_prefix', table_name='discovered_modules')
    op.drop_table('discovered_modules')

    # Drop coding_bit_registry
    op.drop_index('ix_coding_bit_category', table_name='coding_bit_registry')
    op.drop_index('ix_coding_bit_location', table_name='coding_bit_registry')
    op.drop_index('ix_coding_bit_module', table_name='coding_bit_registry')
    op.drop_index('ix_coding_bit_manufacturer', table_name='coding_bit_registry')
    op.drop_table('coding_bit_registry')

    # Drop module_registry
    op.drop_index('ix_module_registry_platforms', table_name='module_registry')
    op.drop_index('ix_module_registry_manufacturer_address', table_name='module_registry')
    op.drop_index('ix_module_registry_manufacturer', table_name='module_registry')
    op.drop_table('module_registry')

    # Drop only the new enums (don't drop manufacturergroup - it's used by PID tables)
    op.execute("DROP TYPE IF EXISTS codingsafetylevel")
    op.execute("DROP TYPE IF EXISTS codingcategory")
