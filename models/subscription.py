import uuid
from sqlalchemy import Column, Text, TIMESTAMP, ForeignKey, Boolean, Integer, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum

from .base import Base

class SubscriptionPlatform(enum.Enum):
    APPLE_APP_STORE = "apple_app_store"
    GOOGLE_PLAY_STORE = "google_play_store"

class SubscriptionStatus(enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELED = "canceled"
    GRACE_PERIOD = "grace_period"
    BILLING_RETRY = "billing_retry"
    PENDING = "pending"

class UserSubscription(Base):
    __tablename__ = "user_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    platform = Column(Enum(SubscriptionPlatform), nullable=False)
    status = Column(Enum(SubscriptionStatus), nullable=False, default=SubscriptionStatus.PENDING)

    # Apple App Store specific fields
    transaction_id = Column(Text, nullable=True)  # Apple's original transaction ID
    product_id = Column(Text, nullable=False)     # Your app's product identifier
    receipt_data = Column(Text, nullable=True)    # Base64 receipt data for validation

    # Subscription timing
    purchase_date = Column(TIMESTAMP, nullable=True)
    expires_date = Column(TIMESTAMP, nullable=True)
    auto_renew_status = Column(Boolean, default=True)

    # Tracking
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    last_validated_at = Column(TIMESTAMP, nullable=True)

    user = relationship("User", back_populates="subscriptions")

class ReceiptValidation(Base):
    __tablename__ = "receipt_validations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_subscription_id = Column(UUID(as_uuid=True), ForeignKey("user_subscriptions.id", ondelete="CASCADE"))
    platform = Column(Enum(SubscriptionPlatform), nullable=False)

    # Raw data from validation
    receipt_data = Column(Text, nullable=False)     # Original receipt
    validation_response = Column(Text, nullable=True)  # Apple's response JSON
    validation_status = Column(Text, nullable=False)   # success/failure/error

    # For debugging and auditing
    created_at = Column(TIMESTAMP, server_default=func.now())

    subscription = relationship("UserSubscription")

class AppStoreNotification(Base):
    __tablename__ = "app_store_notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notification_type = Column(Text, nullable=False)  # INITIAL_BUY, DID_RENEW, etc.
    transaction_id = Column(Text, nullable=True)
    original_transaction_id = Column(Text, nullable=True)
    product_id = Column(Text, nullable=False)

    # Raw notification data for debugging
    raw_payload = Column(Text, nullable=False)
    processed = Column(Boolean, default=False)

    created_at = Column(TIMESTAMP, server_default=func.now())
    processed_at = Column(TIMESTAMP, nullable=True)