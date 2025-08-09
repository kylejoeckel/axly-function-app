# models/service.py
import uuid
from sqlalchemy import (
    Column, Text, TIMESTAMP, Date, ForeignKey,
    Integer, Boolean, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy import Index
from sqlalchemy import text

from .base import Base


class ServicesLibrary(Base):
    """
    Catalog of common service types (e.g., Oil Change, Tire Rotation) with
    optional default intervals for reminders.
    """
    __tablename__ = "services_library"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, unique=True, nullable=False)
    category = Column(Text)              # e.g., Engine, Tires, Brakes
    description = Column(Text)

    # Optional defaults used when creating reminders
    default_interval_miles = Column(Integer)   # e.g., 5000
    default_interval_months = Column(Integer)  # e.g., 6

    created_at = Column(TIMESTAMP, server_default=func.now())

    # backrefs
    services = relationship("VehicleService", back_populates="service_library")
    reminders = relationship("ServiceReminder", back_populates="service_library")


class VehicleService(Base):
    """
    A performed service on a vehicle (think: a dated record + details).
    Mirrors VehicleMod but with service fields like odometer, cost, shop, etc.
    """
    __tablename__ = "vehicle_services"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"))
    service_library_id = Column(UUID(as_uuid=True), ForeignKey("services_library.id"), nullable=True)

    name = Column(Text, nullable=False)         # e.g., Oil Change
    description = Column(Text)                  # notes / what was done
    performed_on = Column(Date)                 # date performed
    odometer_miles = Column(Integer)            # mileage at service

    # Keep money as integer cents to avoid float issues (optional)
    cost_cents = Column(Integer)                # e.g., 6599 for $65.99
    currency = Column(Text, default="USD")      # currency code if you ever need multi-currency

    created_at = Column(TIMESTAMP, server_default=func.now())

    vehicle = relationship("Vehicle", back_populates="services")
    service_library = relationship("ServicesLibrary", back_populates="services")
    documents = relationship("ServiceDocument", back_populates="service", cascade="all, delete-orphan")


class ServiceDocument(Base):
    """
    Attach receipts/photos/etc to a service.
    """
    __tablename__ = "service_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = Column(UUID(as_uuid=True), ForeignKey("vehicle_services.id", ondelete="CASCADE"))
    file_url = Column(Text, nullable=False)
    file_type = Column(Text)  # mime or simple hint (image/jpeg, application/pdf)
    label = Column(Text)      # e.g., "Receipt", "Before photo", "After photo"
    uploaded_at = Column(TIMESTAMP, server_default=func.now())

    service = relationship("VehicleService", back_populates="documents")


class ServiceReminder(Base):
    """
    A reminder configuration for a vehicle service (recurring by miles/time).
    Next-due fields are stored to allow quick queries; your app logic can
    update them whenever a service is performed or reminder is edited.
    """
    __tablename__ = "service_reminders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"))
    service_library_id = Column(UUID(as_uuid=True), ForeignKey("services_library.id"), nullable=True)

    name = Column(Text, nullable=False)     # e.g., Oil Change (can override library name)
    notes = Column(Text)

    # At least one interval should be provided
    interval_miles = Column(Integer)        # e.g., 5000
    interval_months = Column(Integer)       # e.g., 6

    # Tracking last & next due
    last_performed_on = Column(Date)
    last_odometer = Column(Integer)

    next_due_on = Column(Date)
    next_due_miles = Column(Integer)


    remind_ahead_miles = Column(Integer, default=0)    # e.g., alert 300 miles early
    remind_ahead_days = Column(Integer, default=0)     # e.g., alert 7 days early
    is_active = Column(Boolean, nullable=False, server_default=text("true"))

    last_notified_at = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, server_default=func.now())

    vehicle = relationship("Vehicle", back_populates="service_reminders")
    service_library = relationship("ServicesLibrary", back_populates="reminders")

    __table_args__ = (
        CheckConstraint(
            "interval_miles IS NOT NULL OR interval_months IS NOT NULL",
            name="service_reminders_interval_nonnull"
        ),
    )


# Handy indexes (optional, but nice for queries)
Index("ix_vehicle_services_vehicle_date", VehicleService.vehicle_id, VehicleService.performed_on)
Index("ix_service_documents_service", ServiceDocument.service_id)
Index("ix_service_reminders_vehicle_active", ServiceReminder.vehicle_id, ServiceReminder.is_active)
