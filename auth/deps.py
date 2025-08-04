# auth/deps.py
from typing import Optional
from jose import JWTError, jwt

from db import SessionLocal
from models import User
from auth.token import SECRET_KEY, ALGORITHM


def get_current_user(token: str) -> Optional[User]:
    """Decode JWT and return the User, or None if invalid."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            return None
    except JWTError:
        return None

    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    db.close()
    return user


def current_user_from_request(req) -> Optional[User]:
    """Same as above, but pulls the token from Authorization header."""
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    return get_current_user(auth[7:])
