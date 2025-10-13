"""add subscription products

Revision ID: add_products_001
Revises: add_stripe_001
Create Date: 2025-01-13

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_products_001'
down_revision = 'add_stripe_001'
depends_on = None


def upgrade():
    op.create_table(
        'subscription_products',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.String(), nullable=False),
        sa.Column('stripe_price_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('billing_period', sa.String(), nullable=False),
        sa.Column('billing_period_unit', sa.String(), nullable=False),
        sa.Column('popular', sa.Boolean(), nullable=True),
        sa.Column('recommended', sa.Boolean(), nullable=True),
        sa.Column('savings_text', sa.String(), nullable=True),
        sa.Column('trial_available', sa.Boolean(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_id')
    )

    op.execute("""
        INSERT INTO subscription_products (
            product_id, stripe_price_id, name, description,
            billing_period, billing_period_unit, popular, recommended,
            trial_available, sort_order, active
        ) VALUES (
            'stripe_monthly',
            'price_1SHoiNBJjQYYc7gJr9MkTRvN',
            'AXLY Pro Monthly',
            'Unlock all premium features with AI-powered diagnostics',
            'monthly',
            'month',
            true,
            true,
            false,
            1,
            true
        )
    """)


def downgrade():
    op.drop_table('subscription_products')
