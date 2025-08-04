import azure.functions as func
import json, uuid as _uuid, datetime as _dt, logging
from utils.cors import cors_response
from auth.deps import current_user_from_request
from services.vehicle_service import (
    list_vehicles,
    create_vehicle,
    get_vehicle,
    update_vehicle,
    delete_vehicle,
    list_mods,
    add_mod,
    update_mod,
    delete_mod,
)

logger = logging.getLogger(__name__)
bp = func.Blueprint()

# ────────────────────────────────────────────────────────────
#  /vehicles  (collection)
# ────────────────────────────────────────────────────────────
@bp.function_name(name="Vehicles")
@bp.route(route="vehicles",
          methods=["GET", "POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def vehicles(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    if req.method == "GET":
        items = list_vehicles(user.id)
        return cors_response(
            json.dumps([
                {
                    "id":        str(v.id),
                    "make":      v.make,
                    "model":     v.model,
                    "year":      v.year,
                    "created_at": v.created_at.isoformat(),
                } for v in items
            ]),
            200,
            "application/json",
        )

    if req.method == "POST":
        body  = req.get_json()
        make  = body.get("make")
        model = body.get("model")
        year  = body.get("year")
        if not all([make, model, year]):
            return cors_response("Missing make/model/year", 400)
        v = create_vehicle(user.id, make, model, year)
        return cors_response(json.dumps({"id": str(v.id)}), 201, "application/json")


# ────────────────────────────────────────────────────────────
#  /vehicles/{vehicle_id}
# ────────────────────────────────────────────────────────────
@bp.function_name(name="VehicleItem")
@bp.route(route="vehicles/{vehicle_id}",
          methods=["GET", "PUT", "DELETE", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def vehicle_item(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    try:
        vid = _uuid.UUID(req.route_params["vehicle_id"])
    except Exception:
        return cors_response("Invalid vehicle ID", 400)

    if req.method == "GET":
        v = get_vehicle(user.id, vid)
        if not v:
            return cors_response("Not found", 404)
        return cors_response(
            json.dumps({
                "id":    str(v.id),
                "make":  v.make,
                "model": v.model,
                "year":  v.year,
                "mods": [
                    {
                        "id":          str(m.id),
                        "name":        m.name,
                        "description": m.description,
                        "installed_on": (
                            m.installed_on.isoformat() if m.installed_on else None
                        ),
                    } for m in v.mods
                ],
                "created_at": v.created_at.isoformat(),
            }),
            200,
            "application/json",
        )

    if req.method == "PUT":
        ok = update_vehicle(user.id, vid, req.get_json())
        return cors_response("Updated" if ok else "Not found",
                             200 if ok else 404)

    if req.method == "DELETE":
        ok = delete_vehicle(user.id, vid)
        return cors_response("Deleted" if ok else "Not found",
                             200 if ok else 404)


# ────────────────────────────────────────────────────────────
#  /vehicles/{vehicle_id}/mods
# ────────────────────────────────────────────────────────────
@bp.function_name(name="VehicleMods")
@bp.route(route="vehicles/{vehicle_id}/mods",
          methods=["GET", "POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def vehicle_mods(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    try:
        vid = _uuid.UUID(req.route_params["vehicle_id"])
    except Exception:
        return cors_response("Invalid vehicle ID", 400)

    if req.method == "GET":
        mods = list_mods(user.id, vid)
        return cors_response(
            json.dumps([
                {
                    "id":          str(m.id),
                    "name":        m.name,
                    "description": m.description,
                    "installed_on": (
                        m.installed_on.isoformat() if m.installed_on else None
                    ),
                    "created_at":  m.created_at.isoformat(),
                } for m in mods
            ]),
            200,
            "application/json",
        )

    if req.method == "POST":
        body = req.get_json()
        name = body.get("name")
        if not name:
            return cors_response("Missing name", 400)
        desc  = body.get("description", "")
        date_ = body.get("installed_on")
        inst  = _dt.date.fromisoformat(date_) if date_ else None
        m = add_mod(user.id, vid, name, desc, inst)
        if not m:
            return cors_response("Vehicle not found", 404)
        return cors_response(json.dumps({"id": str(m.id)}),
                             201, "application/json")


# ────────────────────────────────────────────────────────────
#  /vehicles/{vehicle_id}/mods/{mod_id}
# ────────────────────────────────────────────────────────────
@bp.function_name(name="VehicleModItem")
@bp.route(route="vehicles/{vehicle_id}/mods/{mod_id}",
          methods=["PUT", "DELETE", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def vehicle_mod_item(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    try:
        vid = _uuid.UUID(req.route_params["vehicle_id"])
        mid = _uuid.UUID(req.route_params["mod_id"])
    except Exception:
        return cors_response("Invalid IDs", 400)

    if req.method == "PUT":
        ok = update_mod(user.id, vid, mid, req.get_json())
        return cors_response("Updated" if ok else "Not found",
                             200 if ok else 404)

    if req.method == "DELETE":
        ok = delete_mod(user.id, vid, mid)
        return cors_response("Deleted" if ok else "Not found",
                             200 if ok else 404)
