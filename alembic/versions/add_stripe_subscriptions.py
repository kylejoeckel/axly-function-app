"""add stripe subscriptions

Revision ID: add_stripe_001
Revises:
Create Date: 2025-01-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'add_stripe_001'
down_revision = '0b644f58a79c'
depends_on = None


def upgrade():
    op.create_table(
        'stripe_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('stripe_customer_id', sa.String(), nullable=False),
        sa.Column('stripe_subscription_id', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('current_period_end', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stripe_subscription_id')
    )


def downgrade():
    op.drop_table('stripe_subscriptions')
