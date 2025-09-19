import hashlib
import json
from datetime import datetime
from typing import Optional, Any

from services.blob_service import upload_bytes, sas_url, _container_client
from utils.pdf import build_vehicle_spec_pdf

SPEC_PDF_CONTAINER = "spec-pdfs"

def _generate_cache_key(vehicle: Any) -> str:
    """Generate a cache key for the vehicle spec PDF based on its data."""
    # Collect all data that would affect the PDF content
    data = {
        'id': str(getattr(vehicle, 'id', '')),
        'make': str(getattr(vehicle, 'make', '')),
        'model': str(getattr(vehicle, 'model', '')),
        'submodel': str(getattr(vehicle, 'submodel', '')),
        'year': str(getattr(vehicle, 'year', '')),
        'vin': str(getattr(vehicle, 'vin', '')),
        'mods': [
            {
                'id': str(getattr(mod, 'id', '')),
                'name': str(getattr(mod, 'name', '')),
                'description': str(getattr(mod, 'description', '')),
                'installed_on': str(getattr(mod, 'installed_on', '')),
                'updated_at': str(getattr(mod, 'updated_at', ''))
            }
            for mod in getattr(vehicle, 'mods', []) or []
        ],
        'services': [
            {
                'id': str(getattr(svc, 'id', '')),
                'name': str(getattr(svc, 'name', '')),
                'description': str(getattr(svc, 'description', '')),
                'performed_on': str(getattr(svc, 'performed_on', '')),
                'updated_at': str(getattr(svc, 'updated_at', ''))
            }
            for svc in getattr(vehicle, 'services', []) or []
        ]
    }
    
    # Generate a deterministic hash of the data
    data_str = json.dumps(data, sort_keys=True)
    return hashlib.sha256(data_str.encode()).hexdigest()

def _get_pdf_blob_name(vehicle_id: str, cache_key: str) -> str:
    """Generate the blob name for a cached PDF."""
    return f"specs/{vehicle_id}/{cache_key}.pdf"

def get_or_generate_spec_pdf(
    vehicle: Any,
    image_bytes: Optional[bytes] = None,
    force_regenerate: bool = False
) -> bytes:
    """Get a cached vehicle spec PDF or generate a new one if needed."""
    vehicle_id = str(getattr(vehicle, 'id', ''))
    cache_key = _generate_cache_key(vehicle)
    blob_name = _get_pdf_blob_name(vehicle_id, cache_key)
    
    # Try to get cached version if not forcing regeneration
    if not force_regenerate:
        try:
            blob_client = _container_client.get_blob_client(blob_name)
            return blob_client.download_blob().readall()
        except Exception:
            # Cache miss or error, fall through to regenerate
            pass
    
    # Generate new PDF
    pdf_bytes = build_vehicle_spec_pdf(
        vehicle,
        image_bytes=image_bytes,
        mods=getattr(vehicle, 'mods', []),
        services=getattr(vehicle, 'services', [])
    )
    
    # Cache the new PDF
    try:
        upload_bytes(
            user_id=str(getattr(vehicle, 'user_id', '')),
            vehicle_id=vehicle_id,
            data=pdf_bytes,
            content_type='application/pdf',
            original_filename=f"spec_{vehicle_id}.pdf"
        )
    except Exception:
        # If caching fails, still return the generated PDF
        pass
    
    return pdf_bytes

def get_cached_spec_pdf_url(vehicle: Any, minutes: int = 60) -> Optional[str]:
    """Get a SAS URL for the cached spec PDF if it exists."""
    vehicle_id = str(getattr(vehicle, 'id', ''))
    cache_key = _generate_cache_key(vehicle)
    blob_name = _get_pdf_blob_name(vehicle_id, cache_key)
    
    try:
        blob_client = _container_client.get_blob_client(blob_name)
        if blob_client.exists():
            return sas_url(blob_name, minutes=minutes)
    except Exception:
        pass
    
    return None