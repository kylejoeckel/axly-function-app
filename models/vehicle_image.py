# models/vehicle_image.py
import uuid
from sqlalchemy import Column, Text, TIMESTAMP, ForeignKey, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .base import Base

class VehicleImage(Base):
    __tablename__ = "vehicle_images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False)
    blob_name = Column(Text, nullable=False)              # e.g. 'users/{uid}/vehicles/{vid}/{uuid}.jpg'
    content_type = Column(Text, nullable=False)
    original_filename = Column(Text)
    width = Column(Integer)
    height = Column(Integer)
    bytes = Column(Integer)
    is_primary = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

    vehicle = relationship("Vehicle", back_populates="images")
