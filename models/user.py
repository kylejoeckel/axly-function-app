import uuid
from sqlalchemy import Column, Text, TIMESTAMP, Boolean, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum

from .base import Base

class UserRole(enum.Enum):
    USER = "user"
    ADMIN = "admin"

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(Text, unique=True, nullable=False)
    password_hash = Column(Text, nullable=True)  # Allow null for App Store-only users
    role = Column(Enum(UserRole), nullable=False, default=UserRole.USER)
    created_via_receipt = Column(Boolean, default=False)  # Track if created via App Store
    created_at = Column(TIMESTAMP, server_default=func.now())

    vehicles = relationship("Vehicle", back_populates="user")
    conversations = relationship("Conversation", back_populates="user")
    subscriptions = relationship("UserSubscription", back_populates="user")

    @property
    def is_app_store_only(self) -> bool:
        """Check if this is an App Store-only account (no password)"""
        return not self.password_hash or self.password_hash == ""

    @property
    def is_admin(self) -> bool:
        """Check if user is an admin"""
        return self.role == UserRole.ADMIN

    @property
    def has_active_subscription(self) -> bool:
        """Check if user has any active subscriptions"""
        from .subscription import SubscriptionStatus
        return any(
            sub.status in [SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE_PERIOD, SubscriptionStatus.BILLING_RETRY]
            for sub in self.subscriptions
        )

    @property
    def requires_subscription(self) -> bool:
        """Check if user requires an active subscription to access the app"""
        return self.role == UserRole.USER  # Only regular users need subscriptions
