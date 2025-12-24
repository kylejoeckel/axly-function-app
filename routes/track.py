import azure.functions as func
import json
import uuid as _uuid
import logging
from utils.cors import cors_response
from auth.deps import current_user_from_request
from services.track_service import (
    list_track_results,
    get_track_result,
    create_track_result,
    delete_track_result,
    get_personal_bests,
    get_track_stats,
)

logger = logging.getLogger(__name__)
bp = func.Blueprint()


def _serialize_result(r, include_vehicle: bool = False) -> dict:
    """Serialize a TrackResult to JSON-compatible dict."""
    data = {
        "id": str(r.id),
        "vehicle_id": str(r.vehicle_id),
        "race_type": r.race_type,
        "tree_type": r.tree_type,
        "elapsed_time": r.elapsed_time,
        "reaction_time": r.reaction_time,
        "trap_speed": r.trap_speed,
        "distance_traveled": r.distance_traveled,
        "is_false_start": r.is_false_start,
        "splits": r.splits,
        "temperature": r.temperature,
        "humidity": r.humidity,
        "altitude": r.altitude,
        "latitude": r.latitude,
        "longitude": r.longitude,
        "location_name": r.location_name,
        "notes": r.notes,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
    if include_vehicle and r.vehicle:
        data["vehicle_make"] = r.vehicle.make
        data["vehicle_model"] = r.vehicle.model
        data["vehicle_year"] = r.vehicle.year
        data["vehicle_submodel"] = r.vehicle.submodel
    return data


@bp.function_name(name="TrackResults")
@bp.route(route="track/results", methods=["GET", "POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def track_results(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    if req.method == "GET":
        # Optional filter by vehicle_id
        vehicle_id = req.params.get("vehicle_id")
        vid = None
        if vehicle_id:
            try:
                vid = _uuid.UUID(vehicle_id)
            except Exception:
                return cors_response("Invalid vehicle_id", 400)

        results = list_track_results(user.id, vid)
        return cors_response(
            json.dumps([_serialize_result(r, include_vehicle=True) for r in results]),
            200,
            "application/json",
        )

    # POST - Create new result
    try:
        body = req.get_json()
    except Exception:
        return cors_response("Invalid JSON body", 400)

    vehicle_id = body.get("vehicle_id")
    race_type = body.get("race_type")
    tree_type = body.get("tree_type")
    elapsed_time = body.get("elapsed_time")

    if not all([vehicle_id, race_type, tree_type, elapsed_time is not None]):
        return cors_response("Missing required fields: vehicle_id, race_type, tree_type, elapsed_time", 400)

    try:
        vid = _uuid.UUID(vehicle_id)
    except Exception:
        return cors_response("Invalid vehicle_id", 400)

    try:
        result = create_track_result(
            user_id=user.id,
            vehicle_id=vid,
            race_type=race_type,
            tree_type=tree_type,
            elapsed_time=int(elapsed_time),
            reaction_time=body.get("reaction_time"),
            trap_speed=body.get("trap_speed"),
            distance_traveled=body.get("distance_traveled"),
            is_false_start=body.get("is_false_start", False),
            splits=body.get("splits"),
            temperature=body.get("temperature"),
            humidity=body.get("humidity"),
            altitude=body.get("altitude"),
            latitude=body.get("latitude"),
            longitude=body.get("longitude"),
            location_name=body.get("location_name"),
            notes=body.get("notes"),
        )
        return cors_response(
            json.dumps({"id": str(result.id)}),
            201,
            "application/json",
        )
    except ValueError as e:
        return cors_response(str(e), 400)
    except Exception as e:
        logger.error(f"Error creating track result: {e}")
        return cors_response("Internal server error", 500)


@bp.function_name(name="TrackResultItem")
@bp.route(route="track/results/{result_id}", methods=["GET", "DELETE", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def track_result_item(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    try:
        result_id = _uuid.UUID(req.route_params["result_id"])
    except Exception:
        return cors_response("Invalid result ID", 400)

    if req.method == "GET":
        result = get_track_result(user.id, result_id)
        if not result:
            return cors_response("Not found", 404)
        return cors_response(
            json.dumps(_serialize_result(result, include_vehicle=True)),
            200,
            "application/json",
        )

    # DELETE
    ok = delete_track_result(user.id, result_id)
    return cors_response("Deleted" if ok else "Not found", 200 if ok else 404)


@bp.function_name(name="TrackPersonalBests")
@bp.route(route="track/results/bests/{vehicle_id}", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def track_personal_bests(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    try:
        vehicle_id = _uuid.UUID(req.route_params["vehicle_id"])
    except Exception:
        return cors_response("Invalid vehicle ID", 400)

    bests = get_personal_bests(user.id, vehicle_id)
    serialized = {
        race_type: (_serialize_result(result) if result else None)
        for race_type, result in bests.items()
    }
    return cors_response(
        json.dumps(serialized),
        200,
        "application/json",
    )


@bp.function_name(name="TrackStats")
@bp.route(route="track/stats", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def track_stats(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    vehicle_id = req.params.get("vehicle_id")
    vid = None
    if vehicle_id:
        try:
            vid = _uuid.UUID(vehicle_id)
        except Exception:
            return cors_response("Invalid vehicle_id", 400)

    stats = get_track_stats(user.id, vid)
    return cors_response(
        json.dumps(stats),
        200,
        "application/json",
    )
