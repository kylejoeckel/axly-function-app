# services/vehicle_service.py
from __future__ import annotations
import uuid
from datetime import date
from typing import List, Optional, Mapping

from sqlalchemy.orm import Session, joinedload

from db import SessionLocal
from models import Vehicle, VehicleMod

# Explicit field allowlists to prevent stray keys (e.g., "image") from breaking updates
VEHICLE_FIELDS = {"make", "model", "submodel", "year"}
MOD_FIELDS     = {"name", "description", "installed_on"}


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
) -> Vehicle:
    with SessionLocal() as db:
        v = Vehicle(user_id=user_id, make=make, model=model, year=year, submodel=submodel)
        db.add(v)
        db.commit()
        db.refresh(v)
        return v


def get_vehicle(user_id: uuid.UUID, vehicle_id: uuid.UUID) -> Optional[Vehicle]:
    with SessionLocal() as db:
        return (
            db.query(Vehicle)
            .options(joinedload(Vehicle.mods))
            .filter(Vehicle.id == vehicle_id, Vehicle.user_id == user_id)
            .first()
        )


def update_vehicle(user_id: uuid.UUID, vehicle_id: uuid.UUID, patch: dict) -> bool:
    """Only allow make/model/submodel/year to be updated. Unknown keys are dropped."""
    patch = _sanitize_patch(patch, VEHICLE_FIELDS)
    if not patch:
        return True  # nothing to change is a no-op success

    with SessionLocal() as db:
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


def delete_mod(user_id: uuid.UUID, vehicle_id: uuid.UUID, mod_id: uuid.UUID) -> bool:
    with SessionLocal() as db:
        rows = (
            db.query(VehicleMod)
            .join(Vehicle, Vehicle.id == VehicleMod.vehicle_id)
            .filter(
                Vehicle.user_id == user_id,
                Vehicle.id == vehicle_id,
                VehicleMod.id == mod_id,
            )
            .delete(synchronize_session=False)
        )
        db.commit()
        return rows > 0


# ───────────── In-memory chat context helpers ──────────────────────────────────
CAR_META: dict[str, dict] = {}  # session_id -> { make, model, submodel, year, mods }

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
