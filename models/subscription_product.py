from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from datetime import datetime
from .base import Base

class SubscriptionProduct(Base):
    __tablename__ = "subscription_products"

    id = Column(Integer, primary_key=True)
    product_id = Column(String, unique=True, nullable=False)
    stripe_price_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text)
    billing_period = Column(String, nullable=False)
    billing_period_unit = Column(String, nullable=False)
    popular = Column(Boolean, default=False)
    recommended = Column(Boolean, default=False)
    savings_text = Column(String, nullable=True)
    trial_available = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
