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


def upgrade() -> None:
    # Create new enums (manufacturergroup already exists from PID migration)
    op.execute("CREATE TYPE codingcategory AS ENUM ('comfort', 'lighting', 'display', 'safety', 'performance', 'audio', 'other')")
    op.execute("CREATE TYPE codingsafetylevel AS ENUM ('safe', 'caution', 'advanced')")

    # Create module_registry table - use existing manufacturergroup type directly
    op.execute("""
        CREATE TABLE module_registry (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            manufacturer manufacturergroup NOT NULL,
            address TEXT NOT NULL,
            name TEXT NOT NULL,
            long_name TEXT,
            can_id TEXT NOT NULL,
            can_id_response TEXT,
            coding_supported BOOLEAN NOT NULL DEFAULT false,
            coding_did TEXT DEFAULT 'F19E',
            coding_length INTEGER,
            platforms TEXT[],
            year_min INTEGER,
            year_max INTEGER,
            is_active BOOLEAN NOT NULL DEFAULT true,
            priority INTEGER NOT NULL DEFAULT 50,
            created_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now()
        )
    """)
    op.create_index('ix_module_registry_manufacturer', 'module_registry', ['manufacturer'], unique=False)
    op.create_index('ix_module_registry_manufacturer_address', 'module_registry', ['manufacturer', 'address'], unique=True)
    op.create_index('ix_module_registry_platforms', 'module_registry', ['platforms'], unique=False, postgresql_using='gin')

    # Create coding_bit_registry table
    op.execute("""
        CREATE TABLE coding_bit_registry (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            manufacturer manufacturergroup NOT NULL,
            module_address TEXT NOT NULL,
            byte_index INTEGER NOT NULL,
            bit_index INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            category codingcategory NOT NULL DEFAULT 'other',
            safety_level codingsafetylevel NOT NULL DEFAULT 'safe',
            platforms TEXT[],
            requires TEXT[],
            conflicts TEXT[],
            is_verified BOOLEAN NOT NULL DEFAULT false,
            source TEXT,
            created_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now()
        )
    """)
    op.create_index('ix_coding_bit_manufacturer', 'coding_bit_registry', ['manufacturer'], unique=False)
    op.create_index('ix_coding_bit_module', 'coding_bit_registry', ['manufacturer', 'module_address'], unique=False)
    op.create_index('ix_coding_bit_location', 'coding_bit_registry', ['manufacturer', 'module_address', 'byte_index', 'bit_index'], unique=True)
    op.create_index('ix_coding_bit_category', 'coding_bit_registry', ['category'], unique=False)

    # Create discovered_modules table
    op.execute("""
        CREATE TABLE discovered_modules (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vin TEXT NOT NULL,
            vin_prefix TEXT NOT NULL,
            manufacturer manufacturergroup NOT NULL,
            module_address TEXT NOT NULL,
            is_present BOOLEAN NOT NULL,
            part_number TEXT,
            software_version TEXT,
            hardware_version TEXT,
            coding_value TEXT,
            device_type TEXT,
            reported_by UUID,
            created_at TIMESTAMP DEFAULT now()
        )
    """)
    op.create_index('ix_discovered_modules_vin_prefix', 'discovered_modules', ['vin_prefix'], unique=False)
    op.create_index('ix_discovered_modules_manufacturer', 'discovered_modules', ['manufacturer'], unique=False)
    op.create_index('ix_discovered_modules_module', 'discovered_modules', ['manufacturer', 'module_address'], unique=False)

    # Create coding_history table
    op.execute("""
        CREATE TABLE coding_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            vehicle_id UUID NOT NULL REFERENCES vehicles(id),
            manufacturer manufacturergroup NOT NULL,
            module_address TEXT NOT NULL,
            coding_before TEXT NOT NULL,
            coding_after TEXT NOT NULL,
            changes JSONB,
            applied_at TIMESTAMP DEFAULT now(),
            reverted BOOLEAN NOT NULL DEFAULT false,
            reverted_at TIMESTAMP
        )
    """)
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
