"""add_vehicle_modules_and_dtcs

Revision ID: add_vehicle_modules_003
Revises: seed_vag_modules_002
Create Date: 2026-01-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'add_vehicle_modules_003'
down_revision: Union[str, Sequence[str], None] = 'seed_vag_modules_002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE vehicle_modules (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vehicle_id UUID NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            manufacturer manufacturergroup NOT NULL,
            module_address TEXT NOT NULL,
            module_name TEXT NOT NULL,
            long_name TEXT,
            is_present BOOLEAN NOT NULL DEFAULT false,
            part_number TEXT,
            software_version TEXT,
            hardware_version TEXT,
            coding_value TEXT,
            coding_supported BOOLEAN NOT NULL DEFAULT false,
            dtc_codes JSONB,
            scanned_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now()
        )
    """)
    op.create_index('ix_vehicle_modules_vehicle', 'vehicle_modules', ['vehicle_id'], unique=False)
    op.create_index('ix_vehicle_modules_user', 'vehicle_modules', ['user_id'], unique=False)
    op.create_index('ix_vehicle_modules_vehicle_address', 'vehicle_modules', ['vehicle_id', 'module_address'], unique=True)

    op.execute("""
        CREATE TABLE module_dtcs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            vehicle_id UUID NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            manufacturer manufacturergroup NOT NULL,
            module_address TEXT NOT NULL,
            module_name TEXT NOT NULL,
            dtc_code TEXT NOT NULL,
            dtc_status TEXT,
            dtc_description TEXT,
            is_active BOOLEAN NOT NULL DEFAULT true,
            is_pending BOOLEAN NOT NULL DEFAULT false,
            is_permanent BOOLEAN NOT NULL DEFAULT false,
            first_seen TIMESTAMP DEFAULT now(),
            last_seen TIMESTAMP DEFAULT now(),
            cleared_at TIMESTAMP
        )
    """)
    op.create_index('ix_module_dtcs_vehicle', 'module_dtcs', ['vehicle_id'], unique=False)
    op.create_index('ix_module_dtcs_user', 'module_dtcs', ['user_id'], unique=False)
    op.create_index('ix_module_dtcs_vehicle_module', 'module_dtcs', ['vehicle_id', 'module_address'], unique=False)
    op.create_index('ix_module_dtcs_code', 'module_dtcs', ['vehicle_id', 'module_address', 'dtc_code'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_module_dtcs_code', table_name='module_dtcs')
    op.drop_index('ix_module_dtcs_vehicle_module', table_name='module_dtcs')
    op.drop_index('ix_module_dtcs_user', table_name='module_dtcs')
    op.drop_index('ix_module_dtcs_vehicle', table_name='module_dtcs')
    op.drop_table('module_dtcs')

    op.drop_index('ix_vehicle_modules_vehicle_address', table_name='vehicle_modules')
    op.drop_index('ix_vehicle_modules_user', table_name='vehicle_modules')
    op.drop_index('ix_vehicle_modules_vehicle', table_name='vehicle_modules')
    op.drop_table('vehicle_modules')
