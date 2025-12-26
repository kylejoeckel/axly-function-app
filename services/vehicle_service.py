# services/vehicle_service.py
from __future__ import annotations
import uuid
from datetime import date
from typing import List, Optional, Mapping
from sqlalchemy import exists, and_, func
from sqlalchemy.orm import joinedload
from db import SessionLocal
from models import (
    Vehicle,
    VehicleMod,
    VehicleService as Svc,
    ServiceDocument as SvcDoc,
    ServiceReminder as SvcRem,
)

VEHICLE_FIELDS = {"make", "model", "submodel", "year", "vin"}


class DuplicateVINError(Exception):
    """Raised when attempting to create/update a vehicle with a VIN that already exists."""
    def __init__(self, vin: str, existing_vehicle: Vehicle):
        self.vin = vin
        self.existing_vehicle = existing_vehicle
        vehicle_name = f"{existing_vehicle.year} {existing_vehicle.make} {existing_vehicle.model}".strip()
        super().__init__(f"A vehicle with VIN '{vin}' already exists: {vehicle_name}")


MOD_FIELDS = {"name", "description", "installed_on"}


def _sanitize_patch(data: Mapping | None, allowed: set[str]) -> dict:
    """Return only keys present in `allowed` and non-None values."""
    if not data:
        return {}
    return {k: v for k, v in data.items() if k in allowed and v is not None}


# ───────────── VEHICLES ────────────────────────────────────────────────────────
def list_vehicles(user_id: uuid.UUID) -> List[Vehicle]:
    with SessionLocal() as db:
        return (
            db.query(Vehicle)
            .filter(Vehicle.user_id == user_id)
            .order_by(Vehicle.created_at.desc())
            .all()
        )


def create_vehicle(
    user_id: uuid.UUID,
    make: str,
    model: str,
    year: str,
    submodel: Optional[str] = None,
    vin: Optional[str] = None,
) -> Vehicle:
    with SessionLocal() as db:
        if vin:
            normalized_vin = vin.upper().strip()
            existing = (
                db.query(Vehicle)
                .filter(
                    Vehicle.user_id == user_id,
                    func.upper(func.trim(Vehicle.vin)) == normalized_vin,
                )
                .first()
            )
            if existing:
                raise DuplicateVINError(vin, existing)

        v = Vehicle(user_id=user_id, make=make, model=model, year=year, submodel=submodel, vin=vin)
        db.add(v)
        db.commit()
        db.refresh(v)
        return v


def get_vehicle(user_id: uuid.UUID, vehicle_id: uuid.UUID) -> Optional[Vehicle]:
    with SessionLocal() as db:
        return (
            db.query(Vehicle)
            .options(joinedload(Vehicle.mods), joinedload(Vehicle.services))
            .filter(Vehicle.id == vehicle_id, Vehicle.user_id == user_id)
            .first()
        )


def update_vehicle(user_id: uuid.UUID, vehicle_id: uuid.UUID, patch: dict) -> bool:
    """Only allow make/model/submodel/year/vin to be updated. Unknown keys are dropped."""
    patch = _sanitize_patch(patch, VEHICLE_FIELDS)
    if not patch:
        return True

    with SessionLocal() as db:
        if "vin" in patch and patch["vin"]:
            normalized_vin = patch["vin"].upper().strip()
            existing = (
                db.query(Vehicle)
                .filter(
                    Vehicle.user_id == user_id,
                    Vehicle.id != vehicle_id,
                    func.upper(func.trim(Vehicle.vin)) == normalized_vin,
                )
                .first()
            )
            if existing:
                raise DuplicateVINError(patch["vin"], existing)

        rows = (
            db.query(Vehicle)
            .filter(Vehicle.id == vehicle_id, Vehicle.user_id == user_id)
            .update(patch, synchronize_session=False)
        )
        db.commit()
        return rows > 0


def delete_vehicle(user_id: uuid.UUID, vehicle_id: uuid.UUID) -> bool:
    with SessionLocal() as db:
        rows = (
            db.query(Vehicle)
            .filter(Vehicle.id == vehicle_id, Vehicle.user_id == user_id)
            .delete(synchronize_session=False)
        )
        db.commit()
        return rows > 0


# ───────────── MODS ────────────────────────────────────────────────────────────
def list_mods(user_id: uuid.UUID, vehicle_id: uuid.UUID) -> List[VehicleMod]:
    with SessionLocal() as db:
        return (
            db.query(VehicleMod)
            .join(Vehicle, Vehicle.id == VehicleMod.vehicle_id)
            .filter(Vehicle.user_id == user_id, Vehicle.id == vehicle_id)
            .order_by(VehicleMod.created_at.desc())
            .all()
        )


def add_mod(
    user_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    name: str,
    description: str = "",
    installed_on: date | None = None,
) -> Optional[VehicleMod]:
    with SessionLocal() as db:
        v = (
            db.query(Vehicle)
            .filter(Vehicle.id == vehicle_id, Vehicle.user_id == user_id)
            .first()
        )
        if not v:
            return None

        m = VehicleMod(
            vehicle_id=vehicle_id,
            name=name,
            description=description,
            installed_on=installed_on,
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        return m


def update_mod(
    user_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    mod_id: uuid.UUID,
    patch: dict,
) -> bool:
    patch = _sanitize_patch(patch, MOD_FIELDS)
    if not patch:
        return True

    with SessionLocal() as db:
        rows = (
            db.query(VehicleMod)
            .join(Vehicle, Vehicle.id == VehicleMod.vehicle_id)
            .filter(
                Vehicle.user_id == user_id,
                Vehicle.id == vehicle_id,
                VehicleMod.id == mod_id,
            )
            .update(patch, synchronize_session=False)
        )
        db.commit()
        return rows > 0


def delete_mod(user_id: _uuid.UUID, vehicle_id: _uuid.UUID, mod_id: _uuid.UUID) -> bool:
    with SessionLocal() as s:
        rows = (
            s.query(VehicleMod)
            .filter(
                VehicleMod.id == mod_id,
                VehicleMod.vehicle_id == vehicle_id,
                exists().where(
                    and_(
                        Vehicle.id == VehicleMod.vehicle_id,
                        Vehicle.user_id == user_id,
                    )
                ),
            )
            .delete(synchronize_session=False)
        )
        s.commit()
        return rows > 0

# ───────────── In-memory chat context helpers ──────────────────────────────────
CAR_META: dict[str, dict] = {}  

def store_vehicle_meta(
    session_id: str,
    make: str,
    model: str,
    year: str,
    mods: str,
    submodel: str | None = None,
):
    """Remember quick vehicle context while a chat session is in memory."""
    if any([make, model, year, mods, submodel]):
        CAR_META[session_id] = dict(make=make, model=model, submodel=submodel, year=year, mods=mods)

def get_vehicle_context(session_id: str) -> str | None:
    meta = CAR_META.get(session_id)
    if not meta:
        return None
    parts = [meta.get("year", "?"), meta.get("make", ""), meta.get("model", "")]
    if meta.get("submodel"):
        parts.append(meta["submodel"])
    car_line = " ".join(p for p in parts if p).strip()
    mods_line = f" (mods: {meta['mods']})" if meta.get("mods") else ""
    return f"Vehicle context: {car_line}{mods_line}"
# ───────────── SERVICES ───────────────────────────────────────────────────────
def list_services(user_id: uuid.UUID, vehicle_id: uuid.UUID) -> List[Svc]:
    with SessionLocal() as db:
        return (
            db.query(Svc)
            .join(Vehicle, Vehicle.id == Svc.vehicle_id)
            .filter(Vehicle.user_id == user_id, Vehicle.id == vehicle_id)
            .order_by(Svc.created_at.desc())
            .all()
        )


def add_service(
    user_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    *,
    name: str,
    description: Optional[str] = None,
    performed_on: Optional[date] = None,
    odometer_miles: Optional[int] = None,
    cost_cents: Optional[int] = None,
    currency: Optional[str] = None,
    service_library_id: Optional[uuid.UUID] = None,
) -> Optional[Svc]:
    with SessionLocal() as db:
        v = (
            db.query(Vehicle)
            .filter(Vehicle.id == vehicle_id, Vehicle.user_id == user_id)
            .first()
        )
        if not v:
            return None

        rec = Svc(
            vehicle_id=vehicle_id,
            name=name,
            description=description or None,
            performed_on=performed_on,
            odometer_miles=odometer_miles,
            cost_cents=cost_cents,
            currency=currency or None,
            service_library_id=service_library_id,
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return rec


def update_service(
    user_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    service_id: uuid.UUID,
    patch: Mapping,
) -> bool:
    patch = _sanitize_patch(dict(patch or {}), SERVICE_FIELDS)
    if not patch:
        return True

    with SessionLocal() as db:
        rows = (
            db.query(Svc)
            .join(Vehicle, Vehicle.id == Svc.vehicle_id)
            .filter(
                Vehicle.user_id == user_id,
                Vehicle.id == vehicle_id,
                Svc.id == service_id,
            )
            .update(patch, synchronize_session=False)
        )
        db.commit()
        return rows > 0


def delete_service(
    user_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    service_id: uuid.UUID,
) -> bool:
    with SessionLocal() as s:
        rows = (
            s.query(Svc)
            .filter(
                Svc.id == service_id,
                Svc.vehicle_id == vehicle_id,
                exists().where(
                    and_(
                        Vehicle.id == Svc.vehicle_id,
                        Vehicle.user_id == user_id,
                    )
                ),
            )
            .delete(synchronize_session=False)
        )
        s.commit()
        return rows > 0

# ───────────── SERVICE DOCUMENTS ──────────────────────────────────────────────
def list_service_documents(
    user_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    service_id: uuid.UUID,
) -> List[SvcDoc]:
    with SessionLocal() as db:
        return (
            db.query(SvcDoc)
            .join(Svc, Svc.id == SvcDoc.service_id)
            .join(Vehicle, Vehicle.id == Svc.vehicle_id)
            .filter(
                Vehicle.user_id == user_id,
                Vehicle.id == vehicle_id,
                Svc.id == service_id,
            )
            .order_by(SvcDoc.uploaded_at.desc())
            .all()
        )


def delete_service_document(
    user_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    service_id: uuid.UUID,
    doc_id: uuid.UUID,
) -> bool:
    with SessionLocal() as s:
        rows = (
            s.query(SvcDoc)
            .join(Svc, Svc.id == SvcDoc.service_id)
            .filter(
                SvcDoc.id == doc_id,
                SvcDoc.service_id == service_id,
                exists().where(
                    and_(
                        Vehicle.id == Svc.vehicle_id,
                        Vehicle.user_id == user_id,
                        Vehicle.id == vehicle_id,
                    )
                ),
            )
            .delete(synchronize_session=False)
        )
        s.commit()
        return rows > 0

# ───────────── SERVICE REMINDERS ──────────────────────────────────────────────
def list_service_reminders(
    user_id: uuid.UUID,
    vehicle_id: uuid.UUID,
) -> List[SvcRem]:
    with SessionLocal() as db:
        return (
            db.query(SvcRem)
            .join(Vehicle, Vehicle.id == SvcRem.vehicle_id)
            .filter(Vehicle.user_id == user_id, Vehicle.id == vehicle_id)
            .order_by(SvcRem.created_at.desc())
            .all()
        )


def add_service_reminder(
    user_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    *,
    name: str,
    notes: Optional[str] = None,
    interval_miles: Optional[int] = None,
    interval_months: Optional[int] = None,
    last_performed_on: Optional[date] = None,
    last_odometer: Optional[int] = None,
    next_due_on: Optional[date] = None,
    next_due_miles: Optional[int] = None,
    remind_ahead_miles: Optional[int] = None,
    remind_ahead_days: Optional[int] = None,
    is_active: bool = True,
    service_library_id: Optional[uuid.UUID] = None,
) -> SvcRem:
    with SessionLocal() as db:
        v = (
            db.query(Vehicle)
            .filter(Vehicle.id == vehicle_id, Vehicle.user_id == user_id)
            .first()
        )
        if not v:
            raise ValueError("Vehicle not found")

        rec = SvcRem(
            vehicle_id=vehicle_id,
            name=name,
            notes=notes or None,
            interval_miles=interval_miles,
            interval_months=interval_months,
            last_performed_on=last_performed_on,
            last_odometer=last_odometer,
            next_due_on=next_due_on,
            next_due_miles=next_due_miles,
            remind_ahead_miles=remind_ahead_miles,
            remind_ahead_days=remind_ahead_days,
            is_active=is_active,
            service_library_id=service_library_id,
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return rec


def update_service_reminder(
    user_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    reminder_id: uuid.UUID,
    patch: Mapping,
) -> bool:
    patch = _sanitize_patch(dict(patch or {}), SERVICE_REM_FIELDS)
    if not patch:
        return True

    with SessionLocal() as db:
        rows = (
            db.query(SvcRem)
            .join(Vehicle, Vehicle.id == SvcRem.vehicle_id)
            .filter(
                Vehicle.user_id == user_id,
                Vehicle.id == vehicle_id,
                SvcRem.id == reminder_id,
            )
            .update(patch, synchronize_session=False)
        )
        db.commit()
        return rows > 0


def delete_service_reminder(
    user_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    reminder_id: uuid.UUID,
) -> bool:
    with SessionLocal() as s:
        rows = (
            s.query(SvcRem)
            .filter(
                SvcRem.id == reminder_id,
                SvcRem.vehicle_id == vehicle_id,
                exists().where(
                    and_(
                        Vehicle.id == SvcRem.vehicle_id,
                        Vehicle.user_id == user_id,
                    )
                ),
            )
            .delete(synchronize_session=False)
        )
        s.commit()
        return rows > 0
