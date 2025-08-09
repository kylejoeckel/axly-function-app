# services/blob_service.py
import os
import uuid
import mimetypes
from typing import Optional, Tuple
from datetime import datetime, timedelta

from azure.storage.blob import (
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
    BlobSasPermissions,
)

# ────────────────────────────────────────────────────────────
# Config
# ────────────────────────────────────────────────────────────
_CONN_STR = os.environ.get("AZURE_BLOB_CONN_STRING")
_CONTAINER = os.environ.get("AZURE_BLOB_CONTAINER", "vehicle-images")

if not _CONN_STR:
    raise RuntimeError(
        "AZURE_BLOB_CONN_STRING is not set. For Azurite, use the devstore connection string."
    )

# Create client + ensure container exists
_bsc = BlobServiceClient.from_connection_string(_CONN_STR)
_container_client = _bsc.get_container_client(_CONTAINER)
try:
    _container_client.create_container()
except Exception:
    # likely already exists
    pass


# ────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────
def _guess_ext(content_type: str, fallback: str = ".bin") -> str:
    exts = mimetypes.guess_all_extensions(content_type) or []
    return exts[0] if exts else fallback


def _parse_account(conn_str: str) -> Tuple[str, Optional[str], str]:
    """
    Returns (account_name, account_key|None, blob_endpoint_base)
    blob_endpoint_base looks like: http://127.0.0.1:10000/devstoreaccount1  (no trailing slash)
    """
    parts = dict(
        kv.split("=", 1)
        for kv in conn_str.split(";")
        if kv and "=" in kv
    )
    account = parts.get("AccountName")
    key = parts.get("AccountKey")
    endpoint = parts.get("BlobEndpoint") or parts.get("BlobEndpointSuffix")
    if not endpoint:
        # Build from primary endpoint on client when not explicit in conn string
        endpoint = _bsc.primary_endpoint  # e.g. https://<acct>.blob.core.windows.net
    # Strip trailing slash if present
    endpoint = endpoint[:-1] if endpoint.endswith("/") else endpoint
    return account, key, endpoint


_ACCOUNT_NAME, _ACCOUNT_KEY, _BLOB_ENDPOINT = _parse_account(_CONN_STR)


def _blob_url(blob_name: str) -> str:
    # Standard form: {endpoint}/{container}/{blob_name}
    return f"{_BLOB_ENDPOINT}/{_CONTAINER}/{blob_name}"


# ────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────
def upload_bytes(
    user_id: str,
    vehicle_id: str,
    data: bytes,
    content_type: str,
    original_filename: Optional[str] = None,
) -> str:
    """
    Upload raw bytes and return the blob_name you can store in DB.
    Pathing: users/{uid}/vehicles/{vid}/{uuid}.{ext}
    """
    ext = _guess_ext(content_type, ".jpg")
    name = f"users/{user_id}/vehicles/{vehicle_id}/{uuid.uuid4()}{ext}"
    blob = _container_client.get_blob_client(name)
    blob.upload_blob(
        data,
        overwrite=False,
        content_settings=ContentSettings(content_type=content_type),
    )
    return name


def sas_url(blob_name: str, minutes: int = 60) -> str:
    """
    Generate a read-only SAS URL for the given blob.
    Requires an account key (works with Azurite and key-based Azure accounts).
    """
    if not _ACCOUNT_KEY:
        # Fallback: just return the public URL (works only if container is public; usually not)
        return _blob_url(blob_name)

    sas = generate_blob_sas(
        account_name=_ACCOUNT_NAME,
        container_name=_CONTAINER,
        blob_name=blob_name,
        account_key=_ACCOUNT_KEY,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(minutes=minutes),
    )
    return f"{_blob_url(blob_name)}?{sas}"


def delete_blob(blob_name: str) -> None:
    """
    Delete a blob; ignores if it doesn't exist.
    """
    try:
        _container_client.delete_blob(blob_name, delete_snapshots="include")
    except Exception:
        # Best-effort delete
        pass
