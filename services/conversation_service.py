"""
services/conversation_service.py
--------------------------------
Chat-history helpers that read/write Conversation and Message rows.

Assumes:
  • SQLAlchemy models in models/conversation.py and models/message.py
  • a SessionLocal() factory in db.py
"""

from __future__ import annotations

import json
import uuid
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session, joinedload
import openai

from db import SessionLocal
from models import Conversation, Message, User, Vehicle

# ────────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ────────────────────────────────────────────────────────────────────────────────


def _ensure_conversation(
    db: Session,
    session_id: Optional[str],
    *,
    user_id: Optional[uuid.UUID] = None,
    vehicle_id: Optional[uuid.UUID] = None,
    title: Optional[str] = None
) -> Conversation:
    """
    • If `session_id` maps to a row, return it.
    • Otherwise create a new Conversation (optionally binding `user_id` / `vehicle_id`)
      and return it.  The caller is responsible for COMMITTING.
    """
    if session_id:
        conv = db.query(Conversation).filter(Conversation.id == session_id).first()
        if conv:
            return conv

    conv = Conversation(
        id=uuid.UUID(session_id) if session_id else uuid.uuid4(),
        user_id=user_id,
        vehicle_id=vehicle_id,
        title=title or "Diagnostic Session",
    )
    db.add(conv)
    return conv


def _load_message_history(db: Session, conv: Conversation) -> List[dict]:
    """
    Convert Message rows to the chat-API dicts you’ve been using.
    """
    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return [{"role": m.sender, "content": json.loads(m.message)} for m in rows]


def _save_message(
    db: Session, conv: Conversation, role: str, content: dict | str
) -> None:
    """
    Persist one chat turn.  `content` is stored as JSON text to round-trip any
    structure (images, transcripts, etc.).
    """
    msg = Message(
        conversation_id=conv.id,
        sender=role,  # 'user' or 'ai'  (CHECK constraint in model)
        message=json.dumps(content, ensure_ascii=False),
    )
    db.add(msg)


# ────────────────────────────────────────────────────────────────────────────────
# Public API – what function_app.py imports
# ────────────────────────────────────────────────────────────────────────────────

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
            history.append({
                "role": msg.sender,
                "content": msg.message
            })
        return history, convo.id

def create_conversation(session_id: str, user_id: UUID, vehicle_id: UUID, title: str, user_msg: dict, ai_msg: dict):
    with SessionLocal() as db:
        convo = Conversation(id=session_id, user_id=user_id, vehicle_id=vehicle_id, title=title)
        db.add(convo)

        db.flush()  # Ensure convo.id is available for FK

        db.add_all([
            Message(conversation_id=convo.id, sender="user", message=json.dumps(user_msg)),
            Message(conversation_id=convo.id, sender="ai", message=json.dumps(ai_msg)),
        ])

        db.commit()
        
def get_or_create_history(
    session_id: Optional[str],
    vehicle_context: Optional[str] = None,
) -> Tuple[List[dict], str]:
    """
    Returns:
        history  – list[dict] ready for OpenAI
        session_id – the conversation UUID (might be newly generated)
    """
    sys_prompt = (
        "You are an **expert** automotive diagnostic assistant. Users are "
        "experienced mechanics.\n\nGuidelines:\n"
        "1. Assume advanced knowledge (OBD-II, wiring diagrams, torque specs).\n"
        "2. **NEVER** say “consult a mechanic.”\n"
        "3. Finish every answer with *Next-step data ▶︎* suggesting photos, "
        "   scope traces, AUDIO, etc. that would refine diagnosis."
    )

    with SessionLocal() as db:
        conv = _ensure_conversation(db, session_id)
        history = _load_message_history(db, conv)

        if not any(m["role"] == "system" for m in history):
            history.insert(0, {"role": "system", "content": sys_prompt})

        if vehicle_context and all(
            v["content"] != vehicle_context for v in history if v["role"] == "system"
        ):
            history.append({"role": "system", "content": vehicle_context})

        db.commit()  
        return history, str(conv.id)

def generate_and_set_title(session_id: str, title_seed: str) -> str:
    """
    Generate a concise (3–8 word) title via OpenAI and update the Conversation row.
    Returns the new title.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant that writes short titles for automotive "
                "diagnostic conversations."
            )
        },
        {
            "role": "user",
            "content": f"Write a concise title (3–8 words) for this question:\n\n{title_seed}"
        }
    ]
    rsp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
    )
    title = rsp.choices[0].message.content.strip().strip('"')

    with SessionLocal() as db:
        conv = db.query(Conversation).filter(Conversation.id == uuid.UUID(session_id)).first()
        if conv:
            conv.title = title
            db.commit()

    return title


def save_conversation(
    session_id: str,
    user_msg: dict,
    assistant_msg: dict,
    title: Optional[str] = None,
) -> None:
    """
    Commit the latest question/answer pair.
    """
    with SessionLocal() as db:
        conv = _ensure_conversation(db, session_id, title=title)
        _save_message(db, conv, role="user", content=user_msg["content"],)
        _save_message(db, conv, role="ai", content=assistant_msg["content"])
        db.commit()

def fetch_conversation(session_id: str) -> dict | None:
    """
    Return a rich dict ready for JSON‑serialisation, or None if not found.
    """

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

def list_conversations(
    *,
    user_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """
    Return basic metadata for many conversations, newest first.

    Query params:
      • user_id – optional filter (as a UUID string)
      • limit / offset – for simple pagination
    """
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
    """
    Remove the Conversation row and all Message rows.
    Returns True if something was deleted.
    """
    with SessionLocal() as db:
        deleted_msgs = db.query(Message).filter(
            Message.conversation_id == uuid.UUID(session_id)
        ).delete()
        deleted_conv = (
            db.query(Conversation).filter(Conversation.id == uuid.UUID(session_id)).delete()
        )
        db.commit()
        return bool(deleted_conv or deleted_msgs)
