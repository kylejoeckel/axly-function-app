import io
import os
import json
import logging
from datetime import datetime
from typing import Optional, Any, Dict, List

import openai
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

try:
    from sqlalchemy.orm.exc import DetachedInstanceError
except Exception:
    class DetachedInstanceError(Exception):
        pass

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

def _fmt_date(dt: Any) -> str:
    if dt is None:
        return "N/A"
    try:
        if hasattr(dt, 'strftime'):
            return dt.strftime('%Y-%m-%d')
        elif isinstance(dt, str):
            from datetime import datetime
            parsed = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            return parsed.strftime('%Y-%m-%d')
        else:
            return str(dt)
    except Exception:
        return str(dt) if dt else "N/A"

def _money(v: Any) -> str:
    try:
        return f"${float(v):,.2f}"
    except Exception:
        return _na(v)

def _safe_rel(obj: Any, attr: str) -> List[Any]:
    try:
        rel = getattr(obj, attr, None)
        if rel is None:
            return []
        return list(rel)
    except DetachedInstanceError:
        logger.debug("Relationship %s is detached; returning empty list", attr)
        return []
    except Exception:
        logger.exception("Failed to read relationship %s", attr)
        return []

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

    make = _na(getattr(vehicle, "make", None))
    model = _na(getattr(vehicle, "model", None))
    submodel = _clean(getattr(vehicle, "submodel", None)) or None
    year = _na(getattr(vehicle, "year", None))

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

        data["estimated_hp"] = _clamp(data.get("estimated_hp"), 40, 2000)
        data["estimated_torque_lbft"] = _clamp(data.get("estimated_torque_lbft"), 40, 2000)
        data["est_0_60_sec"] = _clamp(data.get("est_0_60_sec"), 1.8, 25)
        data["est_quarter_mile_sec"] = _clamp(data.get("est_quarter_mile_sec"), 6, 30)
        data["est_quarter_mile_mph"] = _clamp(data.get("est_quarter_mile_mph"), 40, 300)
        data["est_top_speed_mph"] = _clamp(data.get("est_top_speed_mph"), 60, 300)

        if not isinstance(data.get("assumptions"), list):
            data["assumptions"] = []
        if not isinstance(data.get("confidence"), str) or not data["confidence"]:
            data["confidence"] = "low"

        data["_model_used"] = model_name
        return data

    except Exception:
        logger.exception("AI performance estimate failed")
        return None

def build_vehicle_spec_pdf(
    vehicle,
    image_bytes: Optional[bytes] = None,
    *,
    mods: Optional[List[Any]] = None,
    services: Optional[List[Any]] = None,
) -> bytes:
    buf = io.BytesIO()

    make = _na(getattr(vehicle, 'make', ''))
    model = _na(getattr(vehicle, 'model', ''))
    submodel = _clean(getattr(vehicle, 'submodel', None)) or ""
    year = _na(getattr(vehicle, 'year', ''))

    if mods is None:
        mods = _safe_rel(vehicle, "mods")
    if services is None:
        services = _safe_rel(vehicle, "services")

    title_bits = [year, make, model]
    if submodel:
        title_bits.append(submodel)
    doc_title = f"{' '.join(b for b in title_bits if b)} - Spec Sheet"

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

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleLeft", parent=styles["Title"], alignment=TA_LEFT)
    subtitle_style = ParagraphStyle("SubtitleLeft", parent=styles["Normal"], alignment=TA_LEFT, leading=14)
    h3_left = ParagraphStyle("H3Left", parent=styles["Heading3"], alignment=TA_LEFT)
    small_gray = ParagraphStyle("SmallGray", parent=styles["Normal"], alignment=TA_LEFT, fontSize=8, textColor=colors.grey)

    story: List[Any] = []

    page_title_bits = [year, make, model]
    if submodel:
        page_title_bits.append(submodel)
    page_title = f"<b>{' '.join(b for b in page_title_bits if b)}</b>"
    story.append(Paragraph(page_title, title_style))
    story.append(Paragraph("Vehicle Specification Sheet", subtitle_style))
    story.append(Spacer(1, 0.2 * inch))

    if image_bytes:
        try:
            with PILImage.open(io.BytesIO(image_bytes)) as im:
                w, h = im.size
            max_w = doc.width
            max_h = 3.0 * inch
            scale = min(max_w / w, max_h / h, 1.0)
            img_flowable = RLImage(io.BytesIO(image_bytes), width=w * scale, height=h * scale)
            img_flowable.hAlign = "LEFT"
            story.append(img_flowable)
            story.append(Spacer(1, 0.25 * inch))
        except Exception:
            logger.exception("Failed to place vehicle image")

    spec_data = [
        ["Make", make],
        ["Model", model],
        ["Submodel", submodel or "N/A"],
        ["Year", year],
    ]
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

    est = None
    try:
        est = _estimate_vehicle_performance(vehicle)
    except Exception:
        logger.exception("Performance estimation failed")

    if services:
        story.append(Paragraph("<b>Service History</b>", h3_left))
        rows = [["Service", "Notes", "Performed On", "Odometer", "Cost"]]
        for s in services:
            name = _na(getattr(s, "name", None) or getattr(s, "title", None))

            notes_raw = (
                getattr(s, "description", None)
                or getattr(s, "notes", None)
                or getattr(s, "details", None)
            )
            notes = Paragraph(_na(notes_raw), styles["Normal"])

            dt = (
                getattr(s, "performed_on", None)
                or getattr(s, "date", None)
                or getattr(s, "service_date", None)
                or getattr(s, "created_at", None)
            )
            performed_on = _fmt_date(dt)

            odo = (
                getattr(s, "odometer_miles", None)
                or getattr(s, "odometer", None)
                or getattr(s, "mileage", None)
                or getattr(s, "miles", None)
            )
            odometer = _fmt(odo, "mi")

            cost_val = getattr(s, "cost_cents", None)
            if cost_val is not None:
                try:
                    cost = f"${float(cost_val) / 100:,.2f}"
                except:
                    cost = _na(cost_val)
            else:
                cost_val = (
                    getattr(s, "cost", None)
                    or getattr(s, "price", None)
                    or getattr(s, "amount", None)
                )
                cost = _money(cost_val)

            rows.append([name, notes, performed_on, odometer, cost])

        services_tbl = Table(
            rows,
            colWidths=[1.4 * inch, None, 1.1 * inch, 0.9 * inch, 0.9 * inch],
            repeatRows=1,
        )
        services_tbl.hAlign = "LEFT"
        services_tbl.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(services_tbl)
        story.append(Spacer(1, 0.2 * inch))

    if mods:
        story.append(Paragraph("<b>Installed Modifications</b>", h3_left))
        rows = [["Name", "Description", "Installed On"]]
        for m in mods:
            rows.append([
                _na(getattr(m, "name", None)),
                _na(getattr(m, "description", None)),
                _fmt_date(getattr(m, "installed_on", None)),
            ])
        mods_tbl = Table(rows, colWidths=[1.6 * inch, None, 1.2 * inch])
        mods_tbl.hAlign = "LEFT"
        mods_tbl.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(mods_tbl)
        story.append(Spacer(1, 0.2 * inch))

    if est:
        story.append(Paragraph("<b>Estimated Performance (including mods and sub-model)</b>", h3_left))
        perf_rows = [
            ["Est. Horsepower", _fmt(est.get("estimated_hp"), "hp")],
            ["Est. Torque", _fmt(est.get("estimated_torque_lbft"), "lb-ft")],
            ["Est. 0–60 mph", _fmt(est.get("est_0_60_sec"), "sec", 2)],
            ["Est. 1/4 mile (ET)", _fmt(est.get("est_quarter_mile_sec"), "sec", 2)],
            ["Est. 1/4 mile (trap)", _fmt(est.get("est_quarter_mile_mph"), "mph", 1)],
            ["Est. Top Speed", _fmt(est.get("est_top_speed_mph"), "mph")],
            ["Confidence", _na(est.get("confidence"))],
        ]
        perf_tbl = Table(perf_rows, colWidths=[1.8 * inch, None])
        perf_tbl.hAlign = "LEFT"
        perf_tbl.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(perf_tbl)

        assumptions = est.get("assumptions") or []
        if assumptions:
            story.append(Spacer(1, 0.08 * inch))
            story.append(Paragraph(
                "<b>Assumptions</b>: " + "; ".join(_clean(a) for a in assumptions),
                styles["Normal"],
            ))
        story.append(Spacer(1, 0.2 * inch))

        model_used = est.get("_model_used") or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        story.append(Paragraph(
            f"<font size='8' color='gray'>AI estimates are approximate and for reference only. Model: {model_used}</font>",
            small_gray,
        ))
        story.append(Spacer(1, 0.25 * inch))

    gen = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph(f"<font size='8' color='gray'>Generated by Axly - {gen}</font>", styles["Normal"]))

    doc.build(story)
    buf.seek(0)
    return buf.read()