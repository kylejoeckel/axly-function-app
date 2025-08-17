from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as psql

# revision identifiers, used by Alembic.
revision = '2123b4ab9cdc'          # <-- Alembic filled this
down_revision = 'f8ad74cf588d'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'users',
        sa.Column('id', psql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_unique_constraint('uq_users_email', 'users', ['email'])

    op.create_table(
        'vehicles',
        sa.Column('id', psql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', psql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('year', sa.Integer(), nullable=True),
        sa.Column('make', sa.Text(), nullable=True),
        sa.Column('model', sa.Text(), nullable=True),
        sa.Column('engine', sa.Text(), nullable=True),
        sa.Column('vin', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    op.create_table(
        'conversations',
        sa.Column('id', psql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', psql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('vehicle_id', psql.UUID(as_uuid=True), sa.ForeignKey('vehicles.id', ondelete='SET NULL'), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    op.create_table(
        'messages',
        sa.Column('id', psql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('conversation_id', psql.UUID(as_uuid=True), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sender', sa.String(length=16), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

def downgrade():
    op.drop_table('messages')
    op.drop_table('conversations')
    op.drop_table('vehicles')
    op.drop_constraint('uq_users_email', 'users', type_='unique')
    op.drop_table('users')
