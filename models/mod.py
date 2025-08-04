### models/mod.py
import uuid
from sqlalchemy import Column, Text, TIMESTAMP, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .base import Base

class ModsLibrary(Base):
    __tablename__ = "mods_library"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, unique=True, nullable=False)
    category = Column(Text)
    description = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.now())


class VehicleMod(Base):
    __tablename__ = "vehicle_mods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"))
    mod_library_id = Column(UUID(as_uuid=True), ForeignKey("mods_library.id"), nullable=True)
    name = Column(Text, nullable=False)
    description = Column(Text)
    installed_on = Column(Date)
    created_at = Column(TIMESTAMP, server_default=func.now())

    vehicle = relationship("Vehicle", back_populates="mods")
    documents = relationship("ModDocument", back_populates="mod")


class ModDocument(Base):
    __tablename__ = "mod_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mod_id = Column(UUID(as_uuid=True), ForeignKey("vehicle_mods.id", ondelete="CASCADE"))
    file_url = Column(Text, nullable=False)
    file_type = Column(Text)
    label = Column(Text)
    uploaded_at = Column(TIMESTAMP, server_default=func.now())

    mod = relationship("VehicleMod", back_populates="documents")