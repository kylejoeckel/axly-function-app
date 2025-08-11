from typing import Optional
from db import SessionLocal
from models import User
from auth.token import decode_token

def get_current_user(token: str) -> Optional[User]:
    payload = decode_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    db = SessionLocal()
    try:
        return db.query(User).filter(User.id == user_id).first()
    finally:
        db.close()

def current_user_from_request(req) -> Optional[User]:
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    return get_current_user(auth[7:])
