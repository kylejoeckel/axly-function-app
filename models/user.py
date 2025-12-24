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

class UserTier(enum.Enum):
    FREE = "FREE"
    PREMIUM = "PREMIUM"

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(Text, unique=True, nullable=False)
    password_hash = Column(Text, nullable=True)  # Allow null for App Store-only users
    role = Column(Enum(UserRole), nullable=False, default=UserRole.USER)
    tier = Column(Enum(UserTier), nullable=False, default=UserTier.FREE)
    created_via_receipt = Column(Boolean, default=False)  # Track if created via App Store
    created_at = Column(TIMESTAMP, server_default=func.now())

    vehicles = relationship("Vehicle", back_populates="user")
    conversations = relationship("Conversation", back_populates="user")
    subscriptions = relationship("UserSubscription", back_populates="user")
    stripe_subscription = relationship("StripeSubscription", back_populates="user", uselist=False)
    track_results = relationship("TrackResult", back_populates="user", cascade="all, delete-orphan")

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
    def is_free_tier(self) -> bool:
        """Check if user is on free tier"""
        return self.tier == UserTier.FREE

    @property
    def is_premium_tier(self) -> bool:
        """Check if user is on premium tier"""
        return self.tier == UserTier.PREMIUM

    @property
    def requires_subscription(self) -> bool:
        """Check if user requires an active subscription to access premium features"""
        return self.role == UserRole.USER and self.tier == UserTier.PREMIUM

    @property
    def can_add_vehicles(self) -> bool:
        """Check if user can add more vehicles - unlimited for all users"""
        return True

    @property
    def can_download_spec_sheets(self) -> bool:
        """Check if user can download vehicle spec sheets - available for all users"""
        return True

    @property
    def can_use_diagnose(self) -> bool:
        """Check if user can access diagnose functionality"""
        if self.is_admin:
            return True
        return self.is_premium_tier  # Only premium tier can diagnose
