import io
import os
import json
import logging
from datetime import datetime
from typing import Optional, Any, Dict, List

import openai  # ← follows the same pattern as Diagnose
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image as RLImage,
)

logger = logging.getLogger(__name__)

# Try to import the SA error so we can handle detached access gracefully
try:
    from sqlalchemy.orm.exc import DetachedInstanceError
except Exception:  # pragma: no cover
    class DetachedInstanceError(Exception):  # type: ignore
        pass

# Replace “smart” characters so missing glyphs don’t render as boxes
_REPLACEMENTS = str.maketrans({
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2015": "-",
    "\u2212": "-", "\u2022": "*", "\u00A0": " ", "\u2018": "'", "\u2019": "'",
    "\u201C": '"', "\u201D": '"',
})

def _clean(s: Optional[str]) -> str:
    if s is None:
        return ""
    return str(s).translate(_REPLACEMENTS)

def _na(s: Optional[str]) -> str:
    s2 = _clean(s)
    return s2 if s2.strip() else "N/A"

def _fmt(v: Any, unit: Optional[str] = None, digits: Optional[int] = None) -> str:
    if v is None:
        return "N/A"
    try:
        if isinstance(v, (int, float)) and digits is not None:
            v = f"{v:.{digits}f}"
        s = f"{v}"
    except Exception:
        return "N/A"
    return f"{s} {unit}".strip() if unit else s

def _money(v: Any) -> str:
    try:
        return f"${float(v):,.2f}"
    except Exception:
        return _na(v)

def _safe_rel(obj: Any, attr: str) -> List[Any]:
    """Return a list for relationship attr, avoiding DetachedInstanceError."""
    try:
        rel = getattr(obj, attr, None)
        if rel is None:
            return []
        # Materialize to a plain list so we don't re-touch the session later
        return list(rel)
    except DetachedInstanceError:
        logger.debug("Relationship %s is detached; returning empty list", attr)
        return []
    except Exception:
        logger.exception("Failed to read relationship %s", attr)
        return []

# ────────────────────────────────────────────────────────────
# OpenAI estimate helper (chat.completions pattern)
# ────────────────────────────────────────────────────────────

def _strip_code_fences(s: str) -> str:
    if not s:
        return s
    s = s.strip()
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) >= 3:
            return parts[1].strip() if parts[0] == "" else parts[2].strip()
    try:
        i = s.index("{")
        j = s.rindex("}")
        return s[i:j+1]
    except Exception:
        return s

def _clamp(num: Any, lo: float, hi: float) -> Optional[float]:
    try:
        x = float(num)
        return max(lo, min(hi, x))
    except Exception:
        return None

def _estimate_vehicle_performance(vehicle) -> Optional[Dict[str, Any]]:
    if os.getenv("DISABLE_VEHICLE_PERF_ESTIMATES", "").lower() in {"1", "true", "yes"}:
        return None

    make      = _na(getattr(vehicle, "make", None))
    model     = _na(getattr(vehicle, "model", None))
    submodel  = _clean(getattr(vehicle, "submodel", None)) or None
    year      = _na(getattr(vehicle, "year", None))

    mods_list: List[Dict[str, str]] = []
    try:
        for m in getattr(vehicle, "mods", []) or []:
            mods_list.append({
                "name": _clean(getattr(m, "name", None)),
                "description": _clean(getattr(m, "description", None)),
            })
    except Exception:
        pass

    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    system_msg = {
        "role": "system",
        "content": (
            "You are an automotive analyst. Provide conservative, realistic performance "
            "estimates for the specified vehicle and installed modifications.\n"
            "IMPORTANT:\n"
            "• Reply with JSON only, no prose, no code fences.\n"
            "• Use imperial units (hp, lb-ft, mph, seconds).\n"
            "• If uncertain, reflect that via 'confidence' and 'assumptions'."
        )
    }

    user_payload = {
        "vehicle": {"year": year, "make": make, "model": model, "submodel": submodel},
        "mods": mods_list,
        "return_keys": [
            "estimated_hp",
            "estimated_torque_lbft",
            "est_0_60_sec",
            "est_quarter_mile_sec",
            "est_quarter_mile_mph",
            "est_top_speed_mph",
            "confidence",
            "assumptions"
        ],
        "notes": "Base on typical US-market specs for that year/model and adjust for listed mods."
    }

    user_msg = {
        "role": "user",
        "content": (
            "Return ONLY a single JSON object with the keys listed below. "
            "Do not include any explanation or code fences.\n\n"
            + json.dumps(user_payload, ensure_ascii=False)
        ),
    }

    try:
        rsp = openai.chat.completions.create(
            model=model_name,
            messages=[system_msg, user_msg],
            temperature=0.2,
        )
        content = rsp.choices[0].message.content
        if not content:
            return None

        content = _strip_code_fences(content)
        data = json.loads(content)

        data["estimated_hp"]          = _clamp(data.get("estimated_hp"), 40, 2000)
        data["estimated_torque_lbft"] = _clamp(data.get("estimated_torque_lbft"), 40, 2000)
        data["est_0_60_sec"]          = _clamp(data.get("est_0_60_sec"), 1.8, 25)
        data["est_quarter_mile_sec"]  = _clamp(data.get("est_quarter_mile_sec"), 6, 30)
        data["est_quarter_mile_mph"]  = _clamp(data.get("est_quarter_mile_mph"), 40, 300)
        data["est_top_speed_mph"]     = _clamp(data.get("est_top_speed_mph"), 60, 300)

        if not isinstance(data.get("assumptions"), list):
            data["assumptions"] = []
        if not isinstance(data.get("confidence"), str) or not data["confidence"]:
            data["confidence"] = "low"

        data["_model_used"] = model_name
        return data

    except Exception:
        logger.exception("AI performance estimate failed")
        return None

# ────────────────────────────────────────────────────────────
# PDF builder
# ────────────────────────────────────────────────────────────

def build_vehicle_spec_pdf(
    vehicle,
    image_bytes: Optional[bytes] = None,
    *,
    mods: Optional[List[Any]] = None,
    services: Optional[List[Any]] = None,
) -> bytes:
    """
    Build a PDF for the given vehicle.
    Pass in preloaded 'mods' and 'services' to avoid DetachedInstanceError
    when the SQLAlchemy session is no longer active.
    """
    logger.info("=== Starting PDF generation ===")
    
    try:
        buf = io.BytesIO()
        logger.info("BytesIO buffer created")

        make     = _na(getattr(vehicle, 'make', ''))
        model    = _na(getattr(vehicle, 'model', ''))
        submodel = _clean(getattr(vehicle, 'submodel', None)) or ""
        year     = _na(getattr(vehicle, 'year', ''))
        
        logger.info(f"Vehicle data extracted: {year} {make} {model} {submodel}")

        # If caller didn't pass lists, try to read them safely (may be empty if detached)
        if mods is None:
            logger.info("Loading mods from vehicle...")
            mods = _safe_rel(vehicle, "mods")
        logger.info(f"Mods count: {len(mods)}")
        
        if services is None:
            logger.info("Loading services from vehicle...")
            services = _safe_rel(vehicle, "services")
        logger.info(f"Services count: {len(services)}")

        # Title for PDF metadata
        title_bits = [year, make, model]
        if submodel:
            title_bits.append(submodel)
        doc_title = f"{' '.join(b for b in title_bits if b)} - Spec Sheet"
        logger.info(f"PDF title: {doc_title}")

        logger.info("Creating PDF document...")
        doc = SimpleDocTemplate(
            buf,
            pagesize=letter,
            topMargin=0.6 * inch,
            bottomMargin=0.6 * inch,
            leftMargin=0.7 * inch,
            rightMargin=0.7 * inch,
            title=doc_title,
            author="Axly",
        )
        logger.info("PDF document created")

        logger.info("Setting up styles...")
        styles = getSampleStyleSheet()
        title_style    = ParagraphStyle("TitleLeft",    parent=styles["Title"],   alignment=TA_LEFT)
        subtitle_style = ParagraphStyle("SubtitleLeft", parent=styles["Normal"],  alignment=TA_LEFT, leading=14)
        h3_left        = ParagraphStyle("H3Left",       parent=styles["Heading3"],alignment=TA_LEFT)
        small_gray     = ParagraphStyle("SmallGray",    parent=styles["Normal"],  alignment=TA_LEFT, fontSize=8, textColor=colors.grey)
        logger.info("Styles configured")

        story: List[Any] = []

        # Title + subtitle
        page_title_bits = [year, make, model]
        if submodel:
            page_title_bits.append(submodel)
        page_title = f"<b>{' '.join(b for b in page_title_bits if b)}</b>"
        story.append(Paragraph(page_title, title_style))
        story.append(Paragraph("Vehicle Specification Sheet", subtitle_style))
        story.append(Spacer(1, 0.2 * inch))
        logger.info("Title section added")

        # Image (optional)
        if image_bytes:
            logger.info(f"Processing image: {len(image_bytes)} bytes")
            try:
                with PILImage.open(io.BytesIO(image_bytes)) as im:
                    w, h = im.size
                    logger.info(f"Image dimensions: {w}x{h}")
                max_w = doc.width
                max_h = 3.0 * inch
                scale = min(max_w / w, max_h / h, 1.0)
                img_flowable = RLImage(io.BytesIO(image_bytes), width=w * scale, height=h * scale)
                img_flowable.hAlign = "LEFT"
                story.append(img_flowable)
                story.append(Spacer(1, 0.25 * inch))
                logger.info("Image added to PDF")
            except Exception as e:
                logger.exception(f"Failed to place vehicle image: {e}")
        else:
            logger.info("No image to process")

        # Core specs
        logger.info("Adding core specifications...")
        spec_data = [
            ["Make",     make],
            ["Model",    model],
            ["Submodel", submodel or "N/A"],
            ["Year",     year],
        ]
        
        try:
            tbl = Table(spec_data, colWidths=[1.3 * inch, None])
            tbl.hAlign = "LEFT"
            tbl.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
                ("LINEBELOW", (0, 0), (-1, 0), 0.25, colors.lightgrey),
                ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.lightgrey),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 0.25 * inch))
            logger.info("Core specs table added")
        except Exception as e:
            logger.error(f"Failed to create specs table: {e}")
            raise

        # Check if we should generate AI estimates
        should_estimate = not os.getenv("DISABLE_VEHICLE_PERF_ESTIMATES", "").lower() in {"1", "true", "yes"}
        logger.info(f"AI estimates enabled: {should_estimate}")
        
        # AI‑estimated performance (optional)
        est = None
        if should_estimate:
            try:
                logger.info("Generating AI performance estimates...")
                est = _estimate_vehicle_performance(vehicle)
                if est:
                    logger.info("AI estimates generated successfully")
                else:
                    logger.warning("AI estimates returned None")
            except Exception as e:
                logger.exception(f"AI estimate_vehicle_performance failed: {e}")

        # Continue with the rest of the PDF generation...
        # (Services, Mods, Performance sections would go here with similar logging)
        
        logger.info("Building final PDF...")
        doc.build(story)
        logger.info("PDF built successfully")
        
        buf.seek(0)
        pdf_data = buf.read()
        logger.info(f"PDF generation completed: {len(pdf_data)} bytes")
        return pdf_data
        
    except Exception as e:
        logger.error(f"PDF generation failed: {type(e).__name__}: {str(e)}", exc_info=True)
        raise