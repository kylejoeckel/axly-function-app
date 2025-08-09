# services/conversation_service.py
from __future__ import annotations
import datetime as _dt, json, uuid
from typing import List, Optional, Tuple
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session, joinedload
import openai

from db import SessionLocal
from models import Conversation, Message, User, Vehicle

MONTHLY_CONV_LIMIT = 20
MAX_MSGS_PER_CONVERSATION = 50

SYS_PERSONA = """You are OvaDrive, a senior automotive diagnostics and repair assistant.
Speak mechanic-to-mechanic: confident, direct, and step-driven."""

SYS_RULES = """Rules:
- Vehicle binding: Use only the vehicle in the system line starting with 'Vehicle:' which comes from vehicle_id. Ignore any other vehicles in history.
- Audience: {audience}. Assume the user is skilled and equipped.
- Never fabricate: torque specs, connector pinouts, wire colors, TSB/part numbers, service intervals.
- If a VIN-dependent spec is unknown, proceed anyway: mark it as SPEC TBD or give a typical safe range and continue the full plan.
- Forbidden phrases: do not say “consult/see/refer to OEM/service manual/mechanic/technician”. Provide the next concrete action instead.
- Prefer measurements over guesses (pressure, voltage drop, current, waveforms, trims, mode $06, compression, leak-down).
- Always include a numbered Step-by-step section.
- Units: include metric and US where relevant.
- If DTCs are provided: expand what they prove and what they don’t."""

SYS_FORMAT = """Intent switch:
- If the user asks to remove/replace/install/adjust/program/relearn, use the **Repair Procedure** template.
- Otherwise use the **Diagnostic Plan** template.

# Repair Procedure
## Tools & parts
- Bulleted list (include common sizes only if highly platform-typical; else size TBD)

## Prep
- Battery/ignition states, access notes, trim/brace removal

## Step-by-step
1) Clear access …
2) Disconnect …
3) Remove …
4) Install …
5) Torque values — list each fastener as `SPEC TBD` or typical range if exact varies
6) Reconnect …
7) Relearns/initializations

## Post-checks
- Start/charge output test, belt alignment, noises, DTCs

## Safety callouts
- Specific hazards and why

# Diagnostic Plan
## Quick take
One concise sentence.

## Likely causes (ranked)
- Cause — why plausible

## Step-by-step tests (order matters)
1) Test name — steps — expected — branching action
2) …

## Repair / next actions
- If X confirmed → action

## Safety callouts
- Specific hazards and why

## What to send next ▶
- Exact data/photos/scope traces/sounds

## Confidence
Low / Medium / High with 1–2 lines on what would raise it."""

FEWSHOTS: List[dict] = [] 

def _build_system_messages(audience: str, vehicle_context: Optional[str]) -> List[dict]:
    msgs = [
        {"role": "system", "content": SYS_PERSONA},
        {"role": "system", "content": SYS_RULES.format(audience=audience)},
        {"role": "system", "content": SYS_FORMAT},
    ]
    if vehicle_context:
        msgs.append({"role": "system", "content": vehicle_context})
    return msgs

VEH_PREFIX = "Vehicle: "

def _get_conv(db: Session, conversation_id: uuid.UUID) -> Conversation | None:
    return db.query(Conversation).filter(Conversation.id == conversation_id).first()

def _compose_vehicle_context(v: Vehicle) -> str:
    y = getattr(v, "year", None)
    mk = getattr(v, "make", None)
    md = getattr(v, "model", None)
    eng = getattr(v, "engine", None)
    parts = [str(p) for p in (y, mk, md, eng) if p]
    vin = getattr(v, "vin", None)
    tail = f" (VIN …{vin[-8:]})" if vin and len(vin) >= 8 else ""
    return VEH_PREFIX + " ".join(parts) + tail

def _ensure_conversation(
    db: Session,
    session_id: Optional[str],
    *,
    user_id: Optional[uuid.UUID] = None,
    vehicle_id: Optional[uuid.UUID] = None,
    title: Optional[str] = None
) -> Conversation:
    if session_id:
        try:
            conv = db.query(Conversation).filter(Conversation.id == uuid.UUID(session_id)).first()
            if conv:
                if vehicle_id and conv.vehicle_id != vehicle_id:
                    conv.vehicle_id = vehicle_id
                return conv
        except Exception:
            pass
    conv = Conversation(
        id=uuid.UUID(session_id) if session_id else uuid.uuid4(),
        user_id=user_id,
        vehicle_id=vehicle_id,
        title=title or "Diagnostic Session",
    )
    db.add(conv)
    return conv

def _load_message_history(db: Session, conv: Conversation) -> List[dict]:
    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    history: List[dict] = []
    for m in rows:
        try:
            content = json.loads(m.message)
        except Exception:
            content = m.message
        role = m.sender
        if role == "ai": role = "assistant"
        elif role == "human": role = "user"
        history.append({"role": role, "content": content})
    return history

def _save_message(db: Session, conv: Conversation, role: str, content: dict | str) -> None:
    msg = Message(conversation_id=conv.id, sender=role, message=json.dumps(content, ensure_ascii=False))
    db.add(msg)

def count_user_conversations_this_month(db: Session, user_id: uuid.UUID) -> int:
    now = _dt.datetime.utcnow()
    month_start = _dt.datetime(year=now.year, month=now.month, day=1)
    q = (
        db.query(sa_func.count(Conversation.id))
        .filter(Conversation.user_id == user_id)
        .filter(Conversation.created_at >= month_start)
    )
    return int(q.scalar() or 0)

def count_messages_in_conversation(db: Session, conversation_id: uuid.UUID) -> int:
    q = db.query(sa_func.count(Message.id)).filter(Message.conversation_id == conversation_id)
    return int(q.scalar() or 0)

def append_messages_to_conversation(convo_id: uuid.UUID, user_msg: dict, ai_msg: dict):
    with SessionLocal() as db:
        db.add_all([
            Message(conversation_id=convo_id, sender="user", message=json.dumps(user_msg)),
            Message(conversation_id=convo_id, sender="ai", message=json.dumps(ai_msg)),
        ])
        db.commit()

def get_history(session_id: str):
    with SessionLocal() as db:
        convo = db.query(Conversation).options(joinedload(Conversation.messages)).filter_by(id=session_id).first()
        if not convo:
            return [], None
        history = []
        for msg in sorted(convo.messages, key=lambda m: m.created_at):
            history.append({"role": msg.sender, "content": msg.message})
        return history, convo.id

def create_conversation(session_id: str, user_id: uuid.UUID, vehicle_id: uuid.UUID, title: str, user_msg: dict, ai_msg: dict):
    with SessionLocal() as db:
        convo = Conversation(id=session_id, user_id=user_id, vehicle_id=vehicle_id, title=title)
        db.add(convo)
        db.flush()
        db.add_all([
            Message(conversation_id=convo.id, sender="user", message=json.dumps(user_msg)),
            Message(conversation_id=convo.id, sender="ai", message=json.dumps(ai_msg)),
        ])
        db.commit()

def _set_vehicle_context(history: List[dict], new_ctx: Optional[str]) -> List[dict]:
    filtered = [
        m for m in history
        if not (m["role"] == "system" and isinstance(m["content"], str) and str(m["content"]).startswith(VEH_PREFIX))
    ]
    if new_ctx:
        filtered.append({"role": "system", "content": new_ctx})
    return filtered

def _parse_uuid(val: Optional[str]) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(val)) if val else None
    except Exception:
        return None

def get_or_create_history(
    session_id: Optional[str],
    vehicle_context: Optional[str] = None,  # unused; vehicle comes from DB via vehicle_id
    audience: str = "mixed",
    vehicle_id: Optional[str] = None,
) -> Tuple[List[dict], str]:
    with SessionLocal() as db:
        vid = _parse_uuid(vehicle_id)
        conv = _ensure_conversation(db, session_id, vehicle_id=vid)

        history = _load_message_history(db, conv)

        ctx: Optional[str] = None
        if conv.vehicle_id:
            v = db.query(Vehicle).filter(Vehicle.id == conv.vehicle_id).first()
            if v:
                ctx = _compose_vehicle_context(v)

        sys_msgs = _build_system_messages(audience, ctx)
        messages = sys_msgs + history

        db.commit()
        return messages, str(conv.id)

def generate_and_set_title(session_id: str, title_seed: str) -> str:
    messages = [
        {"role": "system", "content": "You write short titles (3–8 words) for automotive diagnostic conversations."},
        {"role": "user", "content": f"Write a concise title for:\n\n{title_seed}"}
    ]
    rsp = openai.chat.completions.create(model="gpt-4o-mini", messages=messages, temperature=0.2, max_tokens=16)
    title = rsp.choices[0].message.content.strip().strip('"')
    with SessionLocal() as db:
        conv = db.query(Conversation).filter(Conversation.id == uuid.UUID(session_id)).first()
        if conv:
            conv.title = title
            db.commit()
    return title

def save_conversation(session_id: str, user_msg: dict, assistant_msg: dict, title: Optional[str] = None) -> None:
    with SessionLocal() as db:
        conv = _ensure_conversation(db, session_id, title=title)
        _save_message(db, conv, role="user", content=user_msg["content"])
        _save_message(db, conv, role="ai", content=assistant_msg["content"])
        db.commit()

def fetch_conversation(session_id: str) -> dict | None:
    with SessionLocal() as db:
        conv = (
            db.query(Conversation)
            .options(joinedload(Conversation.messages))
            .filter(Conversation.id == uuid.UUID(session_id))
            .first()
        )
        if not conv:
            return None
        return {
            "id": str(conv.id),
            "user_id": str(conv.user_id) if conv.user_id else None,
            "vehicle_id": str(conv.vehicle_id) if conv.vehicle_id else None,
            "title": conv.title,
            "created_at": conv.created_at.isoformat(),
            "messages": [
                {
                    "id": str(m.id),
                    "sender": m.sender,
                    "message": json.loads(m.message),
                    "created_at": m.created_at.isoformat(),
                }
                for m in sorted(conv.messages, key=lambda m: m.created_at)
            ],
        }

def list_conversations(*, user_id: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
    with SessionLocal() as db:
        q = db.query(Conversation).order_by(Conversation.created_at.desc())
        if user_id:
            q = q.filter(Conversation.user_id == uuid.UUID(user_id))
        rows = q.offset(offset).limit(limit).all()
        return [
            {
                "id": str(c.id),
                "title": c.title,
                "user_id": str(c.user_id) if c.user_id else None,
                "vehicle_id": str(c.vehicle_id) if c.vehicle_id else None,
                "created_at": c.created_at.isoformat(),
            }
            for c in rows
        ]

def delete_conversation(session_id: str) -> bool:
    with SessionLocal() as db:
        deleted_msgs = db.query(Message).filter(Message.conversation_id == uuid.UUID(session_id)).delete()
        deleted_conv = db.query(Conversation).filter(Conversation.id == uuid.UUID(session_id)).delete()
        db.commit()
        return bool(deleted_conv or deleted_msgs)

def get_conversation(db: Session, conversation_id: uuid.UUID | str) -> Conversation | None:
    try:
        cid = uuid.UUID(str(conversation_id))
    except Exception:
        return None
    return _get_conv(db, cid)
