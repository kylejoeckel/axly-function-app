import uuid
import enum
from sqlalchemy import Column, Text, TIMESTAMP, Integer, Float, Boolean, Enum, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from .base import Base


class ManufacturerGroup(str, enum.Enum):
    VAG = "VAG"
    BMW = "BMW"
    TOYOTA = "TOYOTA"
    GM = "GM"
    FORD = "FORD"
    STELLANTIS = "STELLANTIS"
    HONDA = "HONDA"
    NISSAN = "NISSAN"
    HYUNDAI = "HYUNDAI"
    MERCEDES = "MERCEDES"
    GENERIC = "GENERIC"


class PIDCategory(str, enum.Enum):
    ENGINE = "engine"
    FUEL = "fuel"
    ELECTRICAL = "electrical"
    TRANSMISSION = "transmission"
    CLIMATE = "climate"
    OTHER = "other"


class PIDRegistry(Base):
    __tablename__ = "pid_registry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pid_id = Column(Text, nullable=False, unique=True)
    name = Column(Text, nullable=False)
    manufacturer = Column(Enum(ManufacturerGroup), nullable=False, default=ManufacturerGroup.GENERIC)
    platform = Column(Text, nullable=True)
    mode = Column(Text, nullable=False)
    pid = Column(Text, nullable=False)
    header = Column(Text, nullable=True)
    formula = Column(Text, nullable=False)
    unit = Column(Text, nullable=False)
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    bytes_count = Column(Integer, nullable=False, default=2)
    category = Column(Enum(PIDCategory), nullable=False, default=PIDCategory.ENGINE)
    priority = Column(Integer, nullable=False, default=10)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_pid_registry_manufacturer", "manufacturer"),
        Index("ix_pid_registry_category", "category"),
        Index("ix_pid_registry_manufacturer_category", "manufacturer", "category"),
    )


class DiscoveredPID(Base):
    __tablename__ = "discovered_pids"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vin = Column(Text, nullable=False)
    vin_prefix = Column(Text, nullable=False)
    manufacturer = Column(Enum(ManufacturerGroup), nullable=False)
    pid_id = Column(Text, nullable=False)
    success = Column(Boolean, nullable=False)
    response_time_ms = Column(Integer, nullable=True)
    raw_response = Column(Text, nullable=True)
    device_type = Column(Text, nullable=True)
    reported_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        Index("ix_discovered_pids_vin_prefix", "vin_prefix"),
        Index("ix_discovered_pids_manufacturer", "manufacturer"),
        Index("ix_discovered_pids_pid_id_success", "pid_id", "success"),
        Index("ix_discovered_pids_vin_prefix_pid", "vin_prefix", "pid_id"),
    )


class PIDProfile(Base):
    __tablename__ = "pid_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vin_prefix = Column(Text, nullable=False, unique=True)
    manufacturer = Column(Enum(ManufacturerGroup), nullable=False)
    platform = Column(Text, nullable=True)
    boost_pid = Column(Text, nullable=True)
    oil_temp_pid = Column(Text, nullable=True)
    charge_air_temp_pid = Column(Text, nullable=True)
    trans_temp_pid = Column(Text, nullable=True)
    working_pids = Column(JSONB, nullable=True, default=list)
    failed_pids = Column(JSONB, nullable=True, default=list)
    sample_count = Column(Integer, nullable=False, default=0)
    confidence = Column(Float, nullable=False, default=0.0)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_pid_profiles_manufacturer", "manufacturer"),
    )
