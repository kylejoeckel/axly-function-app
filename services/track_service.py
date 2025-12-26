# services/track_service.py
from __future__ import annotations
import uuid
from typing import List, Optional, Dict, Any
from sqlalchemy import and_, func as sql_func
from sqlalchemy.orm import joinedload
from db import SessionLocal
from models import TrackResult, Vehicle

VALID_RACE_TYPES = {
    "eighth_mile", "quarter_mile", "half_mile", "mile",
    "0-30", "0-60", "0-100"
}
VALID_TREE_TYPES = {"pro", "sportsman"}


def list_track_results(user_id: uuid.UUID, vehicle_id: Optional[uuid.UUID] = None) -> List[TrackResult]:
    with SessionLocal() as db:
        query = db.query(TrackResult).options(joinedload(TrackResult.vehicle)).filter(TrackResult.user_id == user_id)
        if vehicle_id:
            query = query.filter(TrackResult.vehicle_id == vehicle_id)
        return query.order_by(TrackResult.created_at.desc()).all()


def get_track_result(user_id: uuid.UUID, result_id: uuid.UUID) -> Optional[TrackResult]:
    with SessionLocal() as db:
        return (
            db.query(TrackResult)
            .options(joinedload(TrackResult.vehicle))
            .filter(TrackResult.id == result_id, TrackResult.user_id == user_id)
            .first()
        )


def create_track_result(
    user_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    race_type: str,
    tree_type: str,
    elapsed_time: int,
    reaction_time: Optional[int] = None,
    trap_speed: Optional[float] = None,
    distance_traveled: Optional[float] = None,
    is_false_start: bool = False,
    splits: Optional[List[Dict[str, Any]]] = None,
    temperature: Optional[float] = None,
    humidity: Optional[float] = None,
    altitude: Optional[int] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    location_name: Optional[str] = None,
    notes: Optional[str] = None,
) -> TrackResult:
    if race_type not in VALID_RACE_TYPES:
        raise ValueError(f"Invalid race_type: {race_type}")
    if tree_type not in VALID_TREE_TYPES:
        raise ValueError(f"Invalid tree_type: {tree_type}")

    with SessionLocal() as db:
        # Verify vehicle belongs to user
        vehicle = db.query(Vehicle).filter(
            Vehicle.id == vehicle_id,
            Vehicle.user_id == user_id
        ).first()
        if not vehicle:
            raise ValueError("Vehicle not found or doesn't belong to user")

        result = TrackResult(
            user_id=user_id,
            vehicle_id=vehicle_id,
            race_type=race_type,
            tree_type=tree_type,
            elapsed_time=elapsed_time,
            reaction_time=reaction_time,
            trap_speed=trap_speed,
            distance_traveled=distance_traveled,
            is_false_start=is_false_start,
            splits=splits,
            temperature=temperature,
            humidity=humidity,
            altitude=altitude,
            latitude=latitude,
            longitude=longitude,
            location_name=location_name,
            notes=notes,
        )
        db.add(result)
        db.commit()
        db.refresh(result)
        return result


def delete_track_result(user_id: uuid.UUID, result_id: uuid.UUID) -> bool:
    with SessionLocal() as db:
        rows = (
            db.query(TrackResult)
            .filter(TrackResult.id == result_id, TrackResult.user_id == user_id)
            .delete(synchronize_session=False)
        )
        db.commit()
        return rows > 0


def get_personal_bests(user_id: uuid.UUID, vehicle_id: uuid.UUID) -> Dict[str, Optional[TrackResult]]:
    """Get the best (fastest) result for each race type for a given vehicle."""
    bests: Dict[str, Optional[TrackResult]] = {rt: None for rt in VALID_RACE_TYPES}

    with SessionLocal() as db:
        for race_type in VALID_RACE_TYPES:
            result = (
                db.query(TrackResult)
                .filter(
                    TrackResult.user_id == user_id,
                    TrackResult.vehicle_id == vehicle_id,
                    TrackResult.race_type == race_type,
                    TrackResult.is_false_start == False,
                )
                .order_by(TrackResult.elapsed_time.asc())
                .first()
            )
            bests[race_type] = result

    return bests


def get_track_stats(user_id: uuid.UUID, vehicle_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
    """Get aggregate statistics for track results."""
    with SessionLocal() as db:
        query = db.query(TrackResult).filter(
            TrackResult.user_id == user_id,
            TrackResult.is_false_start == False,
        )
        if vehicle_id:
            query = query.filter(TrackResult.vehicle_id == vehicle_id)

        total_runs = query.count()

        # Count by race type
        by_race_type = {}
        for race_type in VALID_RACE_TYPES:
            count = query.filter(TrackResult.race_type == race_type).count()
            if count > 0:
                by_race_type[race_type] = count

        return {
            "total_runs": total_runs,
            "by_race_type": by_race_type,
        }
