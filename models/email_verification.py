# models.py
import uuid
from datetime import datetime, timedelta
from sqlalchemy import Column, Text, TIMESTAMP, String, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from .base import Base

class EmailVerification(Base):
    __tablename__ = "email_verifications"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email      = Column(Text, nullable=False)
    pin        = Column(Text, nullable=False)  # 6-digit numeric code
    # NEW
    purpose    = Column(String(32), nullable=False, default="signup")  # 'signup' | 'password_reset' | 'change_password'
    expires_at = Column(TIMESTAMP, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

    # Optional: composite index to speed lookups used by your routes
    __table_args__ = (
        Index("ix_email_verifications_email_purpose_pin", "email", "purpose", "pin"),
    )
