import uuid
from sqlalchemy import Column, Text, TIMESTAMP, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .base import Base

class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    make = Column(Text, nullable=False)
    model = Column(Text, nullable=False)
    submodel = Column(Text, nullable=True)  # NEW
    year = Column(Text, nullable=False)
    vin = Column(String(32), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    images = relationship("VehicleImage", back_populates="vehicle", cascade="all, delete-orphan")
    user = relationship("User", back_populates="vehicles")
    mods = relationship("VehicleMod", back_populates="vehicle")
    conversations = relationship("Conversation", back_populates="vehicle")
    # models/vehicle.py (inside Vehicle class)
    services = relationship("VehicleService", back_populates="vehicle", cascade="all, delete-orphan")
    service_reminders = relationship("ServiceReminder", back_populates="vehicle", cascade="all, delete-orphan")

