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
_DEFAULT_CONTAINER = os.environ.get("AZURE_BLOB_CONTAINER", "vehicle-images")

if not _CONN_STR:
    raise RuntimeError(
        "AZURE_BLOB_CONN_STRING is not set. For Azurite, use the devstore connection string."
    )

# Create client
_bsc = BlobServiceClient.from_connection_string(_CONN_STR)

def _get_container_client(container_name: Optional[str] = None) -> Any:
    """Get or create a container client."""
    container = container_name or _DEFAULT_CONTAINER
    client = _bsc.get_container_client(container)
    try:
        client.create_container()
    except Exception:
        # likely already exists
        pass
    return client

# Default container client for backward compatibility
_container_client = _get_container_client(_DEFAULT_CONTAINER)


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


def _blob_url(blob_name: str, container: Optional[str] = None) -> str:
    # Standard form: {endpoint}/{container}/{blob_name}
    container_name = container or _DEFAULT_CONTAINER
    return f"{_BLOB_ENDPOINT}/{container_name}/{blob_name}"


# ────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────
def upload_bytes(
    user_id: str,
    vehicle_id: str,
    data: bytes,
    content_type: str,
    original_filename: Optional[str] = None,
    container: Optional[str] = None,
) -> str:
    """
    Upload raw bytes and return the blob_name you can store in DB.
    Pathing: users/{uid}/vehicles/{vid}/{uuid}.{ext}
    """
    ext = _guess_ext(content_type, ".jpg")
    name = f"users/{user_id}/vehicles/{vehicle_id}/{uuid.uuid4()}{ext}"
    client = _get_container_client(container)
    blob = client.get_blob_client(name)
    blob.upload_blob(
        data,
        overwrite=False,
        content_settings=ContentSettings(content_type=content_type),
    )
    return name


def sas_url(blob_name: str, minutes: int = 60, container: Optional[str] = None) -> str:
    """
    Generate a read-only SAS URL for the given blob.
    Requires an account key (works with Azurite and key-based Azure accounts).
    """
    if not _ACCOUNT_KEY:
        # Fallback: just return the public URL (works only if container is public; usually not)
        return _blob_url(blob_name, container)
    
    container_name = container or _DEFAULT_CONTAINER
    sas = generate_blob_sas(
        account_name=_ACCOUNT_NAME,
        container_name=container_name,
        blob_name=blob_name,
        account_key=_ACCOUNT_KEY,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(minutes=minutes),
    )
    return f"{_blob_url(blob_name, container)}?{sas}"


def delete_blob(blob_name: str, container: Optional[str] = None) -> None:
    """
    Delete a blob; ignores if it doesn't exist.
    """
    try:
        client = _get_container_client(container)
        client.delete_blob(blob_name, delete_snapshots="include")
    except Exception:
        # Best-effort delete
        pass
