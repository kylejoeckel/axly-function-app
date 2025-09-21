import azure.functions as func
from services.blob_service import upload_bytes, sas_url
from services.pdf_cache_service import get_or_generate_spec_pdf
import json, uuid as _uuid, datetime as _dt, logging, requests
from utils.cors import cors_response
from auth.deps import current_user_from_request
from auth.subscription_middleware import require_active_subscription, require_premium_tier
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
    list_services, add_service, update_service, delete_service,
    list_service_documents, delete_service_document,
    list_service_reminders, add_service_reminder, update_service_reminder, delete_service_reminder,
)

# For multipart document uploads (parallel to vehicle_image_service)
from services import service_document_service as sds
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
@require_active_subscription
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
                    "vin":        v.vin,
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
    vin      = body.get("vin")
    if not all([make, model, year]):
        return cors_response("Missing make/model/year", 400)

    # Check if user can add more vehicles (free tier limited to 1)
    if not user.can_add_vehicles:
        return cors_response(
            json.dumps({
                "error": "Vehicle limit reached",
                "current_tier": user.tier.value,
                "max_vehicles": 1 if user.is_free_tier else "unlimited"
            }),
            402,  # Payment Required
            "application/json"
        )

    v = create_vehicle(user.id, make, model, year, submodel=submodel, vin=vin)
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
                "vin":      v.vin,
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
  try:
    if req.method == "OPTIONS":
      # IMPORTANT: pass body + status separately (previously you called cors_response(204))
      return cors_response("", 204)

    user = current_user_from_request(req)
    if not user:
      return cors_response("Unauthorized", 401)

    try:
      vid = _uuid.UUID(req.route_params["vehicle_id"])
      mid = _uuid.UUID(req.route_params["mod_id"])
    except Exception as e:
      logging.warning("Invalid IDs", exc_info=e)
      return cors_response("Invalid IDs", 400)

    if req.method == "PUT":
      try:
        patch = req.get_json() or {}
      except Exception:
        patch = {}
      if "installed_on" in patch and patch["installed_on"]:
        try:
          patch["installed_on"] = _parse_ymd(patch["installed_on"])
        except ValueError as e:
          return cors_response(str(e), 400)
      try:
        ok = update_mod(user.id, vid, mid, patch)
      except Exception as e:
        logging.exception("update_mod failed")
        return cors_response(f"Update failed: {e}", 500)
      return cors_response("Updated" if ok else "Not found", 200 if ok else 404)

    # DELETE
    try:
      ok = delete_mod(user.id, vid, mid)
    except Exception as e:
      logging.exception("delete_mod failed for user=%s vehicle=%s mod=%s", user.id, vid, mid)
      return cors_response(f"Delete failed: {e}", 500)

    if not ok:
      return cors_response("Not found", 404)

    # Return 204 No Content when delete succeeds
    return cors_response("", 204)

  except Exception as e:
    # Absolute last line of defense
    logging.exception("vehicle_mod_item: unhandled")
    return cors_response(f"Internal error: {e}", 500)

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
@require_premium_tier
def vehicle_specsheet(req: func.HttpRequest) -> func.HttpResponse:
    try:
        logger.info("=== VehicleSpecSheet function started ===")
        
        if req.method == "OPTIONS":
            logger.info("OPTIONS request, returning CORS response")
            return cors_response(204)

        logger.info("Authenticating user...")
        user = current_user_from_request(req)
        if not user:
            logger.warning("User authentication failed")
            return cors_response("Unauthorized", 401)
        logger.info(f"User authenticated: {user.id}")

        try:
            vid = _uuid.UUID(req.route_params["vehicle_id"])
            logger.info(f"Vehicle ID parsed: {vid}")
        except Exception as e:
            logger.error(f"Invalid vehicle ID: {e}")
            return cors_response("Invalid vehicle ID", 400)

        logger.info("Fetching vehicle...")
        v = get_vehicle(user.id, vid)
        if not v:
            logger.warning(f"Vehicle not found for user {user.id}, vehicle {vid}")
            return cors_response("Not found", 404)
        logger.info(f"Vehicle found: {v.year} {v.make} {v.model}")

        logger.info("Fetching vehicle image...")
        image_bytes = None
        try:
            img_url = vis.get_primary_image_url(user.id, vid)
            if img_url:
                logger.info(f"Image URL found: {img_url}")
                r = requests.get(img_url, timeout=10)
                if r.ok:
                    image_bytes = r.content
                    logger.info(f"Image downloaded: {len(image_bytes)} bytes")
                else:
                    logger.warning(f"Image download failed: {r.status_code}")
            else:
                logger.info("No image URL found")
        except Exception as e:
            logger.warning(f"Specsheet image fetch failed: {e}", exc_info=True)

        # Generate filename
        name_bits = [str(v.year), str(v.make), str(v.model)]
        if v.submodel:
            name_bits.append(str(v.submodel))
        filename = f"{'-'.join(name_bits)}-specsheet.pdf".replace(" ", "_")
        logger.info(f"Generated filename: {filename}")

        logger.info("Loading vehicle relationships...")
        mods_list = []
        services_list = []
        
        try:
            if hasattr(v, 'mods') and v.mods:
                mods_list = list(v.mods)
                logger.info(f"Loaded {len(mods_list)} mods")
            else:
                logger.info("No mods found or attribute missing")
        except Exception as e:
            logger.warning(f"Could not load mods: {e}")
            
        try:
            if hasattr(v, 'services') and v.services:
                services_list = list(v.services)
                logger.info(f"Loaded {len(services_list)} services")
            else:
                logger.info("No services found or attribute missing")
        except Exception as e:
            logger.warning(f"Could not load services: {e}")

        logger.info("Getting or generating PDF...")
        try:
            pdf_bytes = get_or_generate_spec_pdf(
                v,
                image_bytes=image_bytes,
                force_regenerate=bool(req.params.get('force_regenerate', False))
            )
            logger.info(f"PDF obtained successfully: {len(pdf_bytes)} bytes")
        except Exception as e:
            logger.error(f"PDF retrieval/generation failed: {type(e).__name__}: {str(e)}", exc_info=True)
            return cors_response(f"PDF generation failed: {str(e)}", 500)

        # Store in a temporary blob and generate SAS URL
        logger.info("Creating temporary blob for download...")
        try:
            # Upload the temp file and use the returned blob name for SAS URL
            blob_name = upload_bytes(str(user.id), str(vid), pdf_bytes, "application/pdf", filename)
            url = sas_url(blob_name, minutes=15)  # Short expiry for temp download URLs
            logger.info(f"Temporary download URL generated")
        except Exception as e:
            logger.error(f"Failed to create temporary download: {type(e).__name__}: {str(e)}", exc_info=True)
            return cors_response(f"Failed to create download URL: {str(e)}", 500)
        
        logger.info("=== VehicleSpecSheet function completed successfully ===")
        return cors_response(json.dumps({"url": url, "filename": filename}), 200, "application/json")
        
    except Exception as e:
        logger.error(f"Unexpected error in VehicleSpecSheet: {type(e).__name__}: {str(e)}", exc_info=True)
        return cors_response(f"Internal server error: {str(e)}", 500)

# ─────────────────────────────────────────────────────────────────────────────
# Services collection: GET list / POST create
#   GET  /vehicles/{vehicle_id}/services
#   POST /vehicles/{vehicle_id}/services
# ─────────────────────────────────────────────────────────────────────────────
@bp.function_name(name="VehicleServices")
@bp.route(
    route="vehicles/{vehicle_id}/services",
    methods=["GET", "POST", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def vehicle_services(req: func.HttpRequest) -> func.HttpResponse:
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
            items = list_services(user.id, vid)
        except Exception:
            logger.exception("list_services failed")
            return cors_response("List failed", 500)

        return cors_response(
            json.dumps([
                {
                    "id":           str(s.id),
                    "name":         s.name,
                    "description":  s.description,
                    "performed_on": (s.performed_on.isoformat() if s.performed_on else None),
                    "odometer_miles": s.odometer_miles,
                    "cost_cents":     s.cost_cents,
                    "currency":       s.currency,
                    "created_at":   s.created_at.isoformat() if getattr(s, "created_at", None) else None,
                } for s in items
            ]),
            200,
            "application/json",
        )

    # POST create service
    try:
        body = req.get_json() or {}
    except Exception:
        return cors_response("Invalid JSON", 400)

    name = (body.get("name") or "").strip()
    if not name:
        return cors_response("Missing name", 400)

    desc = body.get("description") or None
    date_ = body.get("performed_on")
    try:
        performed_on = _parse_ymd(date_) if date_ else None
    except ValueError as e:
        return cors_response(str(e), 400)

    odometer_miles = body.get("odometer_miles")
    cost_cents     = body.get("cost_cents")
    currency       = body.get("currency") or None
    svc_lib_id     = body.get("service_library_id") or None

    try:
        rec = add_service(
            user.id, vid,
            name=name,
            description=desc,
            performed_on=performed_on,
            odometer_miles=odometer_miles,
            cost_cents=cost_cents,
            currency=currency,
            service_library_id=svc_lib_id,
        )
        if not rec:
            return cors_response("Vehicle not found", 404)
        return cors_response(json.dumps({"id": str(rec.id)}), 201, "application/json")
    except Exception:
        logger.exception("add_service failed")
        return cors_response("Create failed", 500)


# ─────────────────────────────────────────────────────────────────────────────
# Single service item: PUT update / DELETE remove
#   PUT    /vehicles/{vehicle_id}/services/{service_id}
#   DELETE /vehicles/{vehicle_id}/services/{service_id}
# ─────────────────────────────────────────────────────────────────────────────
@bp.function_name(name="VehicleServiceItem")
@bp.route(
    route="vehicles/{vehicle_id}/services/{service_id}",
    methods=["PUT", "DELETE", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def vehicle_service_item(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    try:
        vid = _uuid.UUID(req.route_params["vehicle_id"])
        sid = _uuid.UUID(req.route_params["service_id"])
    except Exception:
        return cors_response("Invalid IDs", 400)

    if req.method == "PUT":
        try:
            patch = req.get_json() or {}
        except Exception:
            patch = {}

        # parse performed_on if present
        if "performed_on" in patch and patch["performed_on"]:
            try:
                patch["performed_on"] = _parse_ymd(patch["performed_on"])
            except ValueError as e:
                return cors_response(str(e), 400)

        try:
            ok = update_service(user.id, vid, sid, patch)
        except Exception:
            logger.exception("update_service failed")
            return cors_response("Update failed", 500)
        return cors_response("Updated" if ok else "Not found", 200 if ok else 404)

    # DELETE
    try:
        ok = delete_service(user.id, vid, sid)
    except Exception:
        logger.exception("delete_service failed")
        return cors_response("Delete failed", 500)

    if not ok:
        return cors_response("Not found", 404)
    return cors_response("", 204)


# ─────────────────────────────────────────────────────────────────────────────
# Service documents: GET list / POST upload (multipart)
#   GET  /vehicles/{vehicle_id}/services/{service_id}/documents
#   POST /vehicles/{vehicle_id}/services/{service_id}/documents
# ─────────────────────────────────────────────────────────────────────────────
@bp.function_name(name="ServiceDocuments")
@bp.route(
    route="vehicles/{vehicle_id}/services/{service_id}/documents",
    methods=["GET", "POST", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def service_documents(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    try:
        vid = _uuid.UUID(req.route_params["vehicle_id"])
        sid = _uuid.UUID(req.route_params["service_id"])
    except Exception:
        return cors_response("Invalid IDs", 400)

    if req.method == "GET":
        try:
            docs = list_service_documents(user.id, vid, sid)
        except Exception:
            logger.exception("list_service_documents failed")
            return cors_response("List failed", 500)

        return cors_response(
            json.dumps([
                {
                    "id":          str(d.id),
                    "service_id":  str(sid),
                    "file_url":    sds.sign_url(d.file_url, minutes=30),
                    "file_type":   d.file_type,
                    "label":       d.label,
                    "uploaded_at": d.uploaded_at.isoformat() if getattr(d, "uploaded_at", None) else None,
                } for d in docs
            ]),
            200,
            "application/json",
        )

    # POST (multipart) — delegate parsing & blob upload to sds helper
    try:
        rec = sds.upload_document_from_request(user.id, vid, sid, req)
        # Expected to return { id, url, file_type, label, uploaded_at? }
        return cors_response(json.dumps(rec), 201, "application/json")
    except sds.BadRequest as e:
        return cors_response(str(e), 400)
    except sds.NotFound as e:
        return cors_response(str(e), 404)
    except Exception:
        logger.exception("upload service document failed")
        return cors_response("Upload failed", 500)


# ─────────────────────────────────────────────────────────────────────────────
# Single service document: DELETE
#   DELETE /vehicles/{vehicle_id}/services/{service_id}/documents/{doc_id}
# ─────────────────────────────────────────────────────────────────────────────
@bp.function_name(name="ServiceDocumentItem")
@bp.route(
    route="vehicles/{vehicle_id}/services/{service_id}/documents/{doc_id}",
    methods=["DELETE", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def service_document_item(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    try:
        vid = _uuid.UUID(req.route_params["vehicle_id"])
        sid = _uuid.UUID(req.route_params["service_id"])
        did = _uuid.UUID(req.route_params["doc_id"])
    except Exception:
        return cors_response("Invalid IDs", 400)

    try:
        ok = delete_service_document(user.id, vid, sid, did)
    except Exception:
        logger.exception("delete_service_document failed")
        return cors_response("Delete failed", 500)

    if not ok:
        return cors_response("Not found", 404)
    return cors_response("", 204)


# ─────────────────────────────────────────────────────────────────────────────
# Service reminders: GET list / POST create
#   GET  /vehicles/{vehicle_id}/service-reminders
#   POST /vehicles/{vehicle_id}/service-reminders
# ─────────────────────────────────────────────────────────────────────────────
@bp.function_name(name="ServiceReminders")
@bp.route(
    route="vehicles/{vehicle_id}/service-reminders",
    methods=["GET", "POST", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def service_reminders(req: func.HttpRequest) -> func.HttpResponse:
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
            items = list_service_reminders(user.id, vid)
        except Exception:
            logger.exception("list_service_reminders failed")
            return cors_response("List failed", 500)

        return cors_response(
            json.dumps([
                {
                    "id":                    str(r.id),
                    "vehicle_id":            str(vid),
                    "service_library_id":    (str(r.service_library_id) if getattr(r, "service_library_id", None) else None),
                    "name":                  r.name,
                    "notes":                 r.notes,
                    "interval_miles":        r.interval_miles,
                    "interval_months":       r.interval_months,
                    "last_performed_on":     (r.last_performed_on.isoformat() if r.last_performed_on else None),
                    "last_odometer":         r.last_odometer,
                    "next_due_on":           (r.next_due_on.isoformat() if r.next_due_on else None),
                    "next_due_miles":        r.next_due_miles,
                    "remind_ahead_miles":    r.remind_ahead_miles,
                    "remind_ahead_days":     r.remind_ahead_days,
                    "is_active":             r.is_active,
                    "last_notified_at":      (r.last_notified_at.isoformat() if getattr(r, "last_notified_at", None) else None),
                    "created_at":            (r.created_at.isoformat() if getattr(r, "created_at", None) else None),
                } for r in items
            ]),
            200,
            "application/json",
        )

    # POST create reminder
    try:
        body = req.get_json() or {}
    except Exception:
        return cors_response("Invalid JSON", 400)

    name = (body.get("name") or "").strip()
    if not name:
        return cors_response("Missing name", 400)

    # parse dates if provided
    def _maybe_ymd(k):
        v = body.get(k)
        if not v:
            return None
        try:
            return _parse_ymd(v)
        except ValueError as e:
            raise e

    try:
        rec = add_service_reminder(
            user.id, vid,
            name=name,
            notes=body.get("notes") or None,
            interval_miles=body.get("interval_miles"),
            interval_months=body.get("interval_months"),
            last_performed_on=_maybe_ymd("last_performed_on"),
            last_odometer=body.get("last_odometer"),
            next_due_on=_maybe_ymd("next_due_on"),
            next_due_miles=body.get("next_due_miles"),
            remind_ahead_miles=body.get("remind_ahead_miles"),
            remind_ahead_days=body.get("remind_ahead_days"),
            is_active=body.get("is_active", True),
            service_library_id=body.get("service_library_id"),
        )
        return cors_response(json.dumps({"id": str(rec.id)}), 201, "application/json")
    except ValueError as e:
        return cors_response(str(e), 400)
    except Exception:
        logger.exception("add_service_reminder failed")
        return cors_response("Create failed", 500)


# ─────────────────────────────────────────────────────────────────────────────
# Single service reminder: PUT update / DELETE
#   PUT    /vehicles/{vehicle_id}/service-reminders/{reminder_id}
#   DELETE /vehicles/{vehicle_id}/service-reminders/{reminder_id}
# ─────────────────────────────────────────────────────────────────────────────
@bp.function_name(name="ServiceReminderItem")
@bp.route(
    route="vehicles/{vehicle_id}/service-reminders/{reminder_id}",
    methods=["PUT", "DELETE", "OPTIONS"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def service_reminder_item(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    try:
        vid = _uuid.UUID(req.route_params["vehicle_id"])
        rid = _uuid.UUID(req.route_params["reminder_id"])
    except Exception:
        return cors_response("Invalid IDs", 400)

    if req.method == "PUT":
        try:
            patch = req.get_json() or {}
        except Exception:
            patch = {}

        # parse date fields if present
        for k in ("last_performed_on", "next_due_on"):
            if k in patch and patch[k]:
                try:
                    patch[k] = _parse_ymd(patch[k])
                except ValueError as e:
                    return cors_response(str(e), 400)

        try:
            ok = update_service_reminder(user.id, vid, rid, patch)
        except Exception:
            logger.exception("update_service_reminder failed")
            return cors_response("Update failed", 500)
        return cors_response("Updated" if ok else "Not found", 200 if ok else 404)

    # DELETE
    try:
        ok = delete_service_reminder(user.id, vid, rid)
    except Exception:
        logger.exception("delete_service_reminder failed")
        return cors_response("Delete failed", 500)

    if not ok:
        return cors_response("Not found", 404)
    return cors_response("", 204)
