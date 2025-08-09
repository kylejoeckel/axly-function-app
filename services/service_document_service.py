# services/service_document_service.py
from __future__ import annotations

import io
import re
import uuid
import logging
import mimetypes
from datetime import datetime
from email.parser import BytesParser
from email.policy import default as email_default

import azure.functions as func
from db import SessionLocal
from models import Vehicle, VehicleService, ServiceDocument
from services.blob_service import upload_bytes, sas_url

log = logging.getLogger(__name__)


class BadRequest(Exception):
    pass


class NotFound(Exception):
    pass


def _safe_filename(name: str | None, fallback_ext: str = "") -> str:
    base = (name or "").strip()
    if not base:
        base = f"upload-{uuid.uuid4().hex}{fallback_ext}"
    base = base.replace("\\", "/").split("/")[-1]        # strip any path
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)        # sanitize
    return base


def _parse_multipart(req: func.HttpRequest) -> tuple[bytes, str, str, str | None]:
    """
    Returns: (file_bytes, content_type, filename, label)
    Expects a multipart/form-data request with a part named "file" and optional "label".
    """
    ctype = req.headers.get("content-type") or req.headers.get("Content-Type")
    if not ctype or "multipart/form-data" not in ctype.lower():
        raise BadRequest("Content-Type must be multipart/form-data")

    body = req.get_body() or b""

    # Trick: wrap body with a synthetic header so email parser can decode
    synthetic = f"Content-Type: {ctype}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
    msg = BytesParser(policy=email_default).parsebytes(synthetic)

    file_bytes: bytes | None = None
    file_ct: str | None = None
    filename: str | None = None
    label: str | None = None

    # Iterate parts and pick the one named "file"
    for part in msg.iter_parts():
        disp = part.get("Content-Disposition", "")
        if not disp or "form-data" not in disp:
            continue

        # email.message lets us read parameters of the header directly:
        field_name = part.get_param("name", header="content-disposition")
        if field_name == "label":
            try:
                label = (part.get_content() or "").strip()
            except Exception:
                pass
            continue

        if field_name == "file":
            filename = part.get_filename()
            file_ct = part.get_content_type() or None
            file_bytes = part.get_payload(decode=True) or b""

    if file_bytes is None:
        raise BadRequest('Missing "file" field in multipart form-data')

    if not file_ct:
        # guess by filename
        guess, _ = mimetypes.guess_type(filename or "")
        file_ct = guess or "application/octet-stream"

    # add extension if we can guess one
    ext = mimetypes.guess_extension(file_ct) or ""
    filename = _safe_filename(filename, ext)

    return file_bytes, file_ct, filename, label


def _ensure_service_ownership(
    user_id: uuid.UUID, vehicle_id: uuid.UUID, service_id: uuid.UUID
) -> VehicleService:
    with SessionLocal() as db:
        svc = (
            db.query(VehicleService)
            .join(Vehicle, Vehicle.id == VehicleService.vehicle_id)
            .filter(
                Vehicle.user_id == user_id,
                Vehicle.id == vehicle_id,
                VehicleService.id == service_id,
            )
            .first()
        )
        if not svc:
            raise NotFound("Service not found")
        return svc


def sign_url(blob_name: str, minutes: int = 15) -> str:
    """Expose a short-lived URL for a stored blob name."""
    return sas_url(blob_name, minutes=minutes)


def upload_document_from_request(
    user_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    service_id: uuid.UUID,
    req: func.HttpRequest,
) -> dict:
    """
    Parses the multipart request, uploads the file to blob storage,
    creates a ServiceDocument row, and returns a JSON-friendly dict:
    { id, url, file_type, label, uploaded_at }
    """
    _ensure_service_ownership(user_id, vehicle_id, service_id)

    file_bytes, file_ct, filename, label = _parse_multipart(req)

    # Store in blob storage, use service_id as the "asset" folder
    blob_name = upload_bytes(
        str(user_id),
        str(service_id),
        file_bytes,
        file_ct,
        filename,
    )

    with SessionLocal() as db:
        doc = ServiceDocument(
            service_id=service_id,
            file_url=blob_name,    # store blob name; we return a signed URL to clients
            file_type=file_ct,
            label=label or None,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        url = sign_url(doc.file_url, minutes=30)

        return {
            "id": str(doc.id),
            "url": url,
            "file_type": doc.file_type,
            "label": doc.label,
            "uploaded_at": (doc.uploaded_at.isoformat() if getattr(doc, "uploaded_at", None) else None),
        }
