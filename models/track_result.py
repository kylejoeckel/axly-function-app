import uuid
from sqlalchemy import Column, Text, Integer, Float, Boolean, TIMESTAMP, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .base import Base


class TrackResult(Base):
    __tablename__ = "track_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False)

    # Race configuration
    race_type = Column(Text, nullable=False)  # 'quarter_mile', '0-60', etc.
    tree_type = Column(Text, nullable=False)  # 'pro' or 'sportsman'

    # Timing data (stored in milliseconds)
    elapsed_time = Column(Integer, nullable=False)
    reaction_time = Column(Integer, nullable=True)
    trap_speed = Column(Float, nullable=True)  # mph at finish
    distance_traveled = Column(Float, nullable=True)  # feet
    is_false_start = Column(Boolean, default=False)

    # Splits (stored as JSON array)
    splits = Column(JSON, nullable=True)  # [{distance, time, speed}, ...]

    # Conditions (optional)
    temperature = Column(Float, nullable=True)  # °F
    humidity = Column(Float, nullable=True)  # %
    altitude = Column(Integer, nullable=True)  # feet

    # Location (optional)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_name = Column(Text, nullable=True)

    # Metadata
    notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="track_results")
    vehicle = relationship("Vehicle", back_populates="track_results")
