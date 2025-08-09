import azure.functions as func
import uuid, base64, json, logging, datetime as _dt
from utils.cors import cors_response
from services.parser_service      import parse_request
from services.audio_service       import transcribe_audio
from services.conversation_service import (
    MAX_MSGS_PER_CONVERSATION,
    MONTHLY_CONV_LIMIT,
    count_messages_in_conversation,
    count_user_conversations_this_month,
    generate_and_set_title,
    get_or_create_history,
    save_conversation,
    count_messages_in_conversation,
    get_conversation,                    # ← new helper
    MAX_MSGS_PER_CONVERSATION,
    MONTHLY_CONV_LIMIT,
)

import math
from services.vehicle_service import (
    store_vehicle_meta,
    get_vehicle_context,
    get_vehicle,
)
from auth.deps import current_user_from_request
from db import SessionLocal
from models import Conversation
import openai, uuid as _uuid

from routes.state import CONVERSATIONS, CAR_META   # optional, if you still need them

logger = logging.getLogger(__name__)
bp = func.Blueprint()

# ────────────────────────────────────────────────────────────
#  Diagnose – vehicle-ID-based version
# ────────────────────────────────────────────────────────────

def _period_end_iso_utc(now: _dt.datetime | None = None) -> str:
    # first day of next month, 00:00:00 UTC
    now = now or _dt.datetime.utcnow()
    y, m = now.year, now.month
    if m == 12:
        y, m = y + 1, 1
    else:
        m = m + 1
    return _dt.datetime(y, m, 1, 0, 0, 0, tzinfo=_dt.timezone.utc).isoformat()

@bp.function_name(name="DiagnoseV2")
@bp.route(route="diagnose2", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def diagnose_v2(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    try:
        fields      = parse_request(req)
        user_q      = fields["q"]
        session_id  = fields["session_id"] or str(uuid.uuid4())
        vehicle_id  = fields["vehicle_id"]
        image_bytes = fields["image"]
        audio_bytes = fields["audio"]

        if not vehicle_id:
            return cors_response("vehicle_id is required", 400)
        if not any([user_q, image_bytes, audio_bytes]):
            return cors_response("Provide q, image or audio.", 400)

        user = current_user_from_request(req)
        if not user:
            return cors_response("Unauthorized", 401)

        try:
            vid_uuid = _uuid.UUID(vehicle_id)
        except Exception:
            return cors_response("Invalid vehicle_id", 400)

        vehicle = get_vehicle(user.id, vid_uuid)
        if not vehicle:
            return cors_response("Vehicle not found", 404)

        # ─────────── enforce limits BEFORE creating/loading history ───────────
        with SessionLocal() as db:
            conv_uuid = _uuid.UUID(session_id)
            existing = get_conversation(db, conv_uuid)

            if existing is None:
                # starting a brand-new conversation → monthly limit applies
                month_count = count_user_conversations_this_month(db, user.id)
                if month_count >= MONTHLY_CONV_LIMIT:
                    body = {
                        "error": "MONTHLY_LIMIT",
                        "message": "Monthly conversation limit reached.",
                        "limit": MONTHLY_CONV_LIMIT,
                        "period_end": _period_end_iso_utc(),
                    }
                    return cors_response(json.dumps(body), 402, "application/json")

            else:
                # continuing an existing conversation → message cap applies
                msg_count = count_messages_in_conversation(db, conv_uuid)
                # This request would add 2 messages (user + assistant)
                if msg_count >= MAX_MSGS_PER_CONVERSATION - 1:
                    body = {
                        "error": "CONVERSATION_LIMIT",
                        "message": "This conversation has reached its message limit.",
                        "limit": MAX_MSGS_PER_CONVERSATION,
                    }
                    return cors_response(json.dumps(body), 402, "application/json")

        # ─────────── allowed: now build history & proceed ───────────
        mods_txt = ", ".join(
            f"{m.name}{f' – {m.description}' if m.description else ''}" for m in vehicle.mods
        )
        mods_line = f" (mods: {mods_txt})" if mods_txt else ""
        vehicle_context = f"Vehicle context: {vehicle.year} {vehicle.make} {vehicle.model}{mods_line}"

        history, conv_id = get_or_create_history(session_id, vehicle_context)

        # ensure the conversation row is bound to user/vehicle
        with SessionLocal() as db:
            conv = db.query(Conversation).filter(Conversation.id == _uuid.UUID(conv_id)).first()
            if conv:
                if not conv.vehicle_id:
                    conv.vehicle_id = vehicle.id
                if not conv.user_id:
                    conv.user_id = user.id
                db.commit()

        parts: list[dict] = []
        if user_q:
            parts.append({"type": "text", "text": user_q})
        if image_bytes:
            parts.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode()}"
                },
            })
        if audio_bytes:
            transcript, ext = transcribe_audio(audio_bytes)
            parts.append({"type": "text", "text": f"[Audio transcript]\n{transcript}"})
            if ext in ("wav", "mp3"):
                parts.append({
                    "type": "input_audio",
                    "input_audio": {
                        "data": base64.b64encode(audio_bytes).decode(),
                        "format": ext,
                    },
                })

        user_msg = {"role": "user", "content": parts}
        history.append(user_msg)

        rsp = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=history,
        )
        answer = rsp.choices[0].message.content
        assistant_msg = {"role": "assistant", "content": answer}
        history.append(assistant_msg)

        # if first user turn in this convo, generate a title
        with SessionLocal() as db:
            msg_count_now = count_messages_in_conversation(db, _uuid.UUID(conv_id))
        if msg_count_now == 0:
            generate_and_set_title(conv_id, user_q or "Diagnostics")

        save_conversation(conv_id, user_msg, assistant_msg)

        return cors_response(
            json.dumps({"answer": answer, "session_id": conv_id}),
            200,
            "application/json",
        )

    except Exception:
        logger.exception("Error in DiagnoseV2 function")
        # ALWAYS return an HttpResponse here
        return cors_response(
            json.dumps({"error": "SERVER_ERROR", "message": "Server error"}),
            500,
            "application/json",
        )




# ────────────────────────────────────────────────────────────
#  Diagnose – legacy version (no vehicle_id, uses CAR_META)
# ────────────────────────────────────────────────────────────
@bp.function_name(name="Diagnose")
@bp.route(route="Diagnose", methods=["GET", "POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def diagnose(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    try:
        fields      = parse_request(req)
        user_q      = fields["q"]
        session_id  = fields["session_id"] or str(uuid.uuid4())
        make, model = fields["make"], fields["model"]
        year, mods  = fields["year"], fields["mods"]
        image_bytes = fields["image"]
        audio_bytes = fields["audio"]

        if not any([user_q, image_bytes, audio_bytes]):
            return cors_response("Provide q, image or audio.", 400)

        store_vehicle_meta(session_id, make, model, year, mods)
        vehicle_context = get_vehicle_context(session_id)

        history, conv_id = get_or_create_history(session_id, vehicle_context)
        has_user_before  = any(m["role"] == "user" for m in history)

        parts = []
        if user_q:
            parts.append({"type": "text", "text": user_q})
        if image_bytes:
            parts.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode()}"
                },
            })
        if audio_bytes:
            transcript, ext = transcribe_audio(audio_bytes)
            parts.append({"type": "text", "text": f"[Audio transcript]\n{transcript}"})
            if ext in ("wav", "mp3"):
                parts.append({
                    "type": "input_audio",
                    "input_audio": {
                        "data": base64.b64encode(audio_bytes).decode(),
                        "format": ext,
                    },
                })

        user_msg = {"role": "user", "content": parts}
        history.append(user_msg)

        rsp = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=history,
        )
        answer = rsp.choices[0].message.content
        assistant_msg = {"role": "assistant", "content": answer}
        history.append(assistant_msg)

        if not has_user_before:
            generate_and_set_title(session_id, user_q)

        save_conversation(conv_id, user_msg, assistant_msg)

        return cors_response(
            json.dumps({"answer": answer, "session_id": conv_id}),
            200,
            "application/json",
        )

    except Exception:
        logger.exception("Error in Diagnose function")
        return cors_response("Server error", 500)
