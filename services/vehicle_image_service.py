# services/vehicle_image_service.py
import io
import uuid
from typing import Dict, List

from requests_toolbelt.multipart import decoder as mp
from PIL import Image

from db import SessionLocal
from models import Vehicle, VehicleImage
from services.blob_service import upload_bytes, sas_url, delete_blob

# Custom lightweight errors for the routes
class BadRequest(Exception): ...
class NotFound(Exception): ...

ALLOWED_CONTENT = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _parse_multipart(req) -> Dict:
    """
    Parse multipart/form-data from Azure Functions HttpRequest.
    Returns {"filename": ..., "content_type": ..., "data": bytes}
    """
    ctype = req.headers.get("content-type") or req.headers.get("Content-Type")
    if not ctype or "multipart/form-data" not in ctype:
        raise BadRequest("Expected multipart/form-data")

    body = req.get_body()  # bytes
    parts = mp.MultipartDecoder(body, ctype).parts
    if not parts:
        raise BadRequest("No multipart parts found")

    # Expect a field named 'file'
    file_part = None
    for p in parts:
        disp = p.headers.get(b"Content-Disposition", b"").decode("utf-8", "ignore")
        if 'name="file"' in disp:
            file_part = p
            break
    if not file_part:
        # fall back to first file-like part
        file_part = parts[0]

    # filename
    disp = file_part.headers.get(b"Content-Disposition", b"").decode("utf-8", "ignore")
    filename = None
    for token in disp.split(";"):
        token = token.strip()
        if token.startswith("filename="):
            filename = token.split("=", 1)[1].strip().strip('"')
            break
    content_type = file_part.headers.get(b"Content-Type", b"application/octet-stream").decode("utf-8", "ignore")
    data = file_part.content

    if content_type not in ALLOWED_CONTENT:
        raise BadRequest("Unsupported content type")

    if not data:
        raise BadRequest("Empty file")

    return {"filename": filename or "upload.bin", "content_type": content_type, "data": data}


def upload_image_from_request(user_id: uuid.UUID, vehicle_id: uuid.UUID, req) -> Dict:
    """
    Single-image policy:
    - Delete any existing VehicleImage rows + blobs for this vehicle
    - Upload new blob and create a single VehicleImage with is_primary=True
    """
    db = SessionLocal()
    try:
        vehicle = (
            db.query(Vehicle)
            .filter(Vehicle.id == vehicle_id, Vehicle.user_id == user_id)
            .first()
        )
        if not vehicle:
            raise NotFound("Vehicle not found")

        file = _parse_multipart(req)

        # Probe basic image info (non-fatal if fails)
        width = height = None
        try:
            im = Image.open(io.BytesIO(file["data"]))
            width, height = im.size
        except Exception:
            pass

        # Purge existing images for this vehicle (single-image policy)
        existing = (
            db.query(VehicleImage)
            .filter(VehicleImage.vehicle_id == vehicle_id)
            .all()
        )
        for r in existing:
            try:
                delete_blob(r.blob_name)
            except Exception:
                # don't fail the whole request on blob delete race; keep going
                pass
            db.delete(r)
        db.flush()  # ensure deletes are staged before insert

        # Upload new blob
        blob_name = upload_bytes(
            str(user_id),
            str(vehicle_id),
            file["data"],
            file["content_type"],
            file["filename"],
        )

        # Insert single image as primary
        row = VehicleImage(
            vehicle_id=vehicle.id,
            blob_name=blob_name,
            content_type=file["content_type"],
            original_filename=file["filename"],
            width=width,
            height=height,
            bytes=len(file["data"]),
            is_primary=True,
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        return {
            "id": str(row.id),
            "url": sas_url(row.blob_name, minutes=60),
            "contentType": row.content_type,
            "width": row.width,
            "height": row.height,
            "bytes": row.bytes,
            "isPrimary": row.is_primary,
            "createdAt": row.created_at.isoformat() if row.created_at else None,
        }
    finally:
        db.close()


def list_images(user_id: uuid.UUID, vehicle_id: uuid.UUID) -> List[Dict]:
    db = SessionLocal()
    try:
        v = (
            db.query(Vehicle)
            .filter(Vehicle.id == vehicle_id, Vehicle.user_id == user_id)
            .first()
        )
        if not v:
            raise NotFound("Vehicle not found")

        rows = (
            db.query(VehicleImage)
            .filter(VehicleImage.vehicle_id == vehicle_id)
            .order_by(VehicleImage.created_at.desc())
            .all()
        )
        return [
            {
                "id": str(r.id),
                "url": sas_url(r.blob_name, minutes=60),
                "contentType": r.content_type,
                "width": r.width,
                "height": r.height,
                "bytes": r.bytes,
                "isPrimary": r.is_primary,
                "createdAt": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        db.close()


def delete_image(user_id: uuid.UUID, vehicle_id: uuid.UUID, image_id: uuid.UUID) -> bool:
    db = SessionLocal()
    try:
        row = (
            db.query(VehicleImage)
            .join(Vehicle, Vehicle.id == VehicleImage.vehicle_id)
            .filter(
                VehicleImage.id == image_id,
                VehicleImage.vehicle_id == vehicle_id,
                Vehicle.user_id == user_id,
            )
            .first()
        )
        if not row:
            return False

        try:
            delete_blob(row.blob_name)
        except Exception:
            # swallow blob delete errors; we still remove DB record
            pass

        db.delete(row)
        db.commit()
        return True
    finally:
        db.close()


def set_primary(user_id: uuid.UUID, vehicle_id: uuid.UUID, image_id: uuid.UUID) -> bool:
    """
    Kept for API compatibility. With single-image policy, the only image is primary.
    If somehow multiple exist, this still flips flags correctly.
    """
    db = SessionLocal()
    try:
        exists = (
            db.query(VehicleImage)
            .join(Vehicle, Vehicle.id == VehicleImage.vehicle_id)
            .filter(
                VehicleImage.id == image_id,
                VehicleImage.vehicle_id == vehicle_id,
                Vehicle.user_id == user_id,
            )
            .first()
        )
        if not exists:
            return False

        db.execute(
            VehicleImage.__table__.update()
            .where(VehicleImage.vehicle_id == vehicle_id)
            .values(is_primary=False)
        )
        db.execute(
            VehicleImage.__table__.update()
            .where(VehicleImage.id == image_id)
            .values(is_primary=True)
        )
        db.commit()
        return True
    finally:
        db.close()


def get_primary_image_url(user_id: uuid.UUID, vehicle_id: uuid.UUID, ttl_minutes: int = 60) -> str | None:
    db = SessionLocal()
    try:
        img = (
            db.query(VehicleImage)
            .join(Vehicle, Vehicle.id == VehicleImage.vehicle_id)
            .filter(
                Vehicle.user_id == user_id,
                VehicleImage.vehicle_id == vehicle_id
            )
            .order_by(VehicleImage.is_primary.desc(), VehicleImage.created_at.desc())
            .first()
        )
        if not img:
            return None
        return sas_url(img.blob_name, minutes=ttl_minutes)
    finally:
        db.close()
# NEW: delete the (single) image for a vehicle
def delete_vehicle_image(user_id: uuid.UUID, vehicle_id: uuid.UUID) -> bool:
    db = SessionLocal()
    try:
        rows = (
            db.query(VehicleImage)
            .join(Vehicle, Vehicle.id == VehicleImage.vehicle_id)
            .filter(
                Vehicle.user_id == user_id,
                VehicleImage.vehicle_id == vehicle_id,
            )
            .all()
        )
        if not rows:
            return False
        for r in rows:
            try:
                delete_blob(r.blob_name)
            except Exception:
                pass
            db.delete(r)
        db.commit()
        return True
    finally:
        db.close()

# OPTIONAL aliases (keep names consistent if any code still calls them)
def get_vehicle_image_url(user_id: uuid.UUID, vehicle_id: uuid.UUID, ttl_minutes: int = 60):
    return get_primary_image_url(user_id, vehicle_id, ttl_minutes)

def upload_or_replace_image(user_id: uuid.UUID, vehicle_id: uuid.UUID, req):
    return upload_image_from_request(user_id, vehicle_id, req)
