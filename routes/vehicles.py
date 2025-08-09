import azure.functions as func
from services.blob_service import upload_bytes, sas_url
from utils.pdf import build_vehicle_spec_pdf 
import json, uuid as _uuid, datetime as _dt, logging, requests
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
from services import vehicle_image_service as vis  # for primary image URLs

logger = logging.getLogger(__name__)
bp = func.Blueprint()

def _parse_ymd(s: str) -> _dt.date:
    try:
        y, m, d = (int(p) for p in s.strip().split("-"))
        return _dt.date(y, m, d)
    except Exception:
        raise ValueError(f"Invalid date (expected YYYY-MM-DD): {s!r}")


@bp.function_name(name="Vehicles")
@bp.route(route="vehicles", methods=["GET", "POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
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
                    "id":         str(v.id),
                    "make":       v.make,
                    "model":      v.model,
                    "submodel":   v.submodel,
                    "year":       v.year,
                    "image":      vis.get_primary_image_url(user.id, v.id) or None,
                    "created_at": v.created_at.isoformat(),
                }
                for v in items
            ]),
            200,
            "application/json",
        )

    # POST
    body     = req.get_json()
    make     = body.get("make")
    model    = body.get("model")
    year     = body.get("year")
    submodel = body.get("submodel")
    if not all([make, model, year]):
        return cors_response("Missing make/model/year", 400)
    v = create_vehicle(user.id, make, model, year, submodel=submodel)
    return cors_response(json.dumps({"id": str(v.id)}), 201, "application/json")

@bp.function_name(name="VehicleItem")
@bp.route(route="vehicles/{vehicle_id}", methods=["GET", "PUT", "DELETE", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
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
                "id":       str(v.id),
                "make":     v.make,
                "model":    v.model,
                "submodel": v.submodel,
                "year":     v.year,
                "image":    vis.get_primary_image_url(user.id, v.id) or None,
                "mods": [
                    {
                        "id":           str(m.id),
                        "name":         m.name,
                        "description":  m.description,
                        "installed_on": (m.installed_on.isoformat() if m.installed_on else None),
                    } for m in v.mods
                ],
                "created_at": v.created_at.isoformat(),
            }),
            200,
            "application/json",
        )

    if req.method == "PUT":
        patch = req.get_json() or {}
        ok = update_vehicle(user.id, vid, patch)
        return cors_response("Updated" if ok else "Not found", 200 if ok else 404)

    # DELETE
    ok = delete_vehicle(user.id, vid)
    return cors_response("Deleted" if ok else "Not found", 200 if ok else 404)

@bp.function_name(name="VehicleMods")
@bp.route(route="vehicles/{vehicle_id}/mods", methods=["GET", "POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
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
                    "id":           str(m.id),
                    "name":         m.name,
                    "description":  m.description,
                    "installed_on": (m.installed_on.isoformat() if m.installed_on else None),
                    "created_at":   m.created_at.isoformat(),
                } for m in mods
            ]),
            200,
            "application/json",
        )

    body = req.get_json()
    name = body.get("name")
    if not name:
        return cors_response("Missing name", 400)
    desc  = body.get("description", "")
    date_ = body.get("installed_on")
    try:
        inst = _parse_ymd(date_) if date_ else None
    except ValueError as e:
        return cors_response(str(e), 400)

    m = add_mod(user.id, vid, name, desc, inst)
    if not m:
        return cors_response("Vehicle not found", 404)
    return cors_response(json.dumps({"id": str(m.id)}), 201, "application/json")

@bp.function_name(name="VehicleModItem")
@bp.route(route="vehicles/{vehicle_id}/mods/{mod_id}", methods=["PUT", "DELETE", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
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
        patch = req.get_json() or {}
        if "installed_on" in patch and patch["installed_on"]:
            try:
                patch["installed_on"] = _parse_ymd(patch["installed_on"])
            except ValueError as e:
                return cors_response(str(e), 400)
        ok = update_mod(user.id, vid, mid, patch)
        return cors_response("Updated" if ok else "Not found", 200 if ok else 404)

    ok = delete_mod(user.id, vid, mid)
    return cors_response("Deleted" if ok else "Not found", 200 if ok else 404)

@bp.function_name(name="VehicleImage")
@bp.route(route="vehicles/{vehicle_id}/image", methods=["GET", "POST", "DELETE", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def vehicle_image(req: func.HttpRequest) -> func.HttpResponse:
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
        try:
            url = vis.get_primary_image_url(user.id, vid) or None
            return cors_response(json.dumps({"url": url}), 200, "application/json")
        except Exception:
            logger.exception("lookup image failed")
            return cors_response("Lookup failed", 500)

    if req.method == "POST":
        try:
            rec = vis.upload_image_from_request(user.id, vid, req)
            return cors_response(json.dumps({"url": rec.get("url")}), 201, "application/json")
        except vis.BadRequest as e:
            return cors_response(str(e), 400)
        except vis.NotFound as e:
            return cors_response(str(e), 404)
        except Exception:
            logger.exception("upload/replace image failed")
            return cors_response("Upload failed", 500)

    try:
        ok = vis.delete_vehicle_image(user.id, vid)
        return cors_response("Deleted" if ok else "Not found", 200 if ok else 404)
    except Exception:
        logger.exception("delete image failed")
        return cors_response("Delete failed", 500)

@bp.function_name(name="VehicleSpecSheet")
@bp.route(route="vehicles/{vehicle_id}/specsheet", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def vehicle_specsheet(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    try:
        vid = _uuid.UUID(req.route_params["vehicle_id"])
    except Exception:
        return cors_response("Invalid vehicle ID", 400)

    v = get_vehicle(user.id, vid)
    if not v:
        return cors_response("Not found", 404)

    image_bytes = None
    try:
        img_url = vis.get_primary_image_url(user.id, vid)
        if img_url:
            r = requests.get(img_url, timeout=10)
            if r.ok:
                image_bytes = r.content
    except Exception:
        logger.warning("Specsheet image fetch failed", exc_info=True)

    # include submodel in filename if present
    name_bits = [v.year, v.make, v.model]
    if v.submodel:
        name_bits.append(v.submodel)
    filename = f"{'-'.join(name_bits)}-specsheet.pdf".replace(" ", "_")

    try:
        pdf_bytes = build_vehicle_spec_pdf(v, image_bytes=image_bytes)
        blob_name = upload_bytes(str(user.id), str(vid), pdf_bytes, "application/pdf", filename)
        url = sas_url(blob_name, minutes=15)
        return cors_response(json.dumps({"url": url, "filename": filename}), 200, "application/json")
    except Exception:
        logger.exception("Failed to generate spec sheet")
        return cors_response("Failed to generate spec sheet", 500)
