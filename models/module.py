"""
ECU Module and Coding Bit models for manufacturer-specific diagnostics
"""
import uuid
import enum
from sqlalchemy import Column, Text, TIMESTAMP, Integer, Boolean, Enum, Index, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.sql import func
from .base import Base
from .pid import ManufacturerGroup


class CodingCategory(str, enum.Enum):
    COMFORT = "comfort"
    LIGHTING = "lighting"
    DISPLAY = "display"
    SAFETY = "safety"
    PERFORMANCE = "performance"
    AUDIO = "audio"
    OTHER = "other"

    def __str__(self):
        return self.value


class CodingSafetyLevel(str, enum.Enum):
    SAFE = "safe"
    CAUTION = "caution"
    ADVANCED = "advanced"

    def __str__(self):
        return self.value


class ModuleRegistry(Base):
    """
    Registry of ECU modules for each manufacturer.
    Stores module addresses, names, CAN IDs, and coding support info.
    """
    __tablename__ = "module_registry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Module identification
    manufacturer = Column(Enum(ManufacturerGroup), nullable=False)
    address = Column(Text, nullable=False)  # e.g., "17" for VAG, "7E0" for generic
    name = Column(Text, nullable=False)  # Short name
    long_name = Column(Text, nullable=True)  # Full name with part description

    # CAN communication
    can_id = Column(Text, nullable=False)  # CAN ID for addressing (hex string)
    can_id_response = Column(Text, nullable=True)  # Response CAN ID if different

    # Coding support
    coding_supported = Column(Boolean, nullable=False, default=False)
    coding_did = Column(Text, nullable=True, default="F19E")  # Data ID for reading coding
    coding_length = Column(Integer, nullable=True)  # Expected coding length in bytes

    # Platform support
    platforms = Column(ARRAY(Text), nullable=True)  # ["MQB", "MLB", "PQ35"]
    year_min = Column(Integer, nullable=True)
    year_max = Column(Integer, nullable=True)

    # Metadata
    is_active = Column(Boolean, nullable=False, default=True)
    priority = Column(Integer, nullable=False, default=50)  # For scan ordering
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_module_registry_manufacturer", "manufacturer"),
        Index("ix_module_registry_manufacturer_address", "manufacturer", "address", unique=True),
        Index("ix_module_registry_platforms", "platforms", postgresql_using="gin"),
    )


class CodingBitRegistry(Base):
    """
    Registry of known coding bits for each module.
    Labels what each bit does (e.g., "Needle Sweep", "Comfort Windows").
    """
    __tablename__ = "coding_bit_registry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Module reference
    manufacturer = Column(Enum(ManufacturerGroup), nullable=False)
    module_address = Column(Text, nullable=False)  # e.g., "17"

    # Bit location
    byte_index = Column(Integer, nullable=False)  # 0-based byte index
    bit_index = Column(Integer, nullable=False)  # 0-7 bit index within byte

    # Bit information
    name = Column(Text, nullable=False)  # Display name
    description = Column(Text, nullable=True)  # What this bit does
    category = Column(Enum(CodingCategory, values_callable=lambda x: [e.value for e in x], create_type=False), nullable=False, default=CodingCategory.OTHER)
    safety_level = Column(Enum(CodingSafetyLevel, values_callable=lambda x: [e.value for e in x], create_type=False), nullable=False, default=CodingSafetyLevel.SAFE)

    # Platform support
    platforms = Column(ARRAY(Text), nullable=True)  # Which platforms support this

    # Dependencies
    requires = Column(ARRAY(Text), nullable=True)  # Other codings needed first
    conflicts = Column(ARRAY(Text), nullable=True)  # Mutually exclusive codings

    # Metadata
    is_verified = Column(Boolean, nullable=False, default=False)  # Community verified
    source = Column(Text, nullable=True)  # Where this came from (e.g., "ross-tech-wiki")
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_coding_bit_manufacturer", "manufacturer"),
        Index("ix_coding_bit_module", "manufacturer", "module_address"),
        Index("ix_coding_bit_location", "manufacturer", "module_address", "byte_index", "bit_index", unique=True),
        Index("ix_coding_bit_category", "category"),
    )


class DiscoveredModule(Base):
    """
    Crowdsourced module discovery data from users.
    Tracks which modules are present on specific VIN prefixes.
    """
    __tablename__ = "discovered_modules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Vehicle identification
    vin = Column(Text, nullable=False)
    vin_prefix = Column(Text, nullable=False)  # First 11 chars for matching
    manufacturer = Column(Enum(ManufacturerGroup), nullable=False)

    # Module data
    module_address = Column(Text, nullable=False)
    is_present = Column(Boolean, nullable=False)
    part_number = Column(Text, nullable=True)
    software_version = Column(Text, nullable=True)
    hardware_version = Column(Text, nullable=True)
    coding_value = Column(Text, nullable=True)  # Raw coding bytes (hex)

    # Discovery metadata
    device_type = Column(Text, nullable=True)  # BLE adapter model
    reported_by = Column(UUID(as_uuid=True), nullable=True)  # User ID
    created_at = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        Index("ix_discovered_modules_vin_prefix", "vin_prefix"),
        Index("ix_discovered_modules_manufacturer", "manufacturer"),
        Index("ix_discovered_modules_module", "manufacturer", "module_address"),
    )


class CodingHistory(Base):
    """
    User's coding change history (for rollback support).
    Stored when user applies coding changes (ENTHUSIAST tier).
    """
    __tablename__ = "coding_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # References
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False)

    # Module and coding
    manufacturer = Column(Enum(ManufacturerGroup), nullable=False)
    module_address = Column(Text, nullable=False)
    coding_before = Column(Text, nullable=False)  # Hex string
    coding_after = Column(Text, nullable=False)  # Hex string

    # What was changed (for display)
    changes = Column(JSONB, nullable=True)  # [{bit: "Needle Sweep", from: false, to: true}]

    # Status
    applied_at = Column(TIMESTAMP, server_default=func.now())
    reverted = Column(Boolean, nullable=False, default=False)
    reverted_at = Column(TIMESTAMP, nullable=True)

    __table_args__ = (
        Index("ix_coding_history_user", "user_id"),
        Index("ix_coding_history_vehicle", "vehicle_id"),
        Index("ix_coding_history_user_vehicle", "user_id", "vehicle_id"),
    )
