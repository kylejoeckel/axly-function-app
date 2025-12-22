import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

import jwt
from jwt.exceptions import PyJWTError as JWTError
import logging

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fallback-secret-key")
REFRESH_SECRET_KEY = os.getenv("JWT_REFRESH_SECRET_KEY", SECRET_KEY + "-refresh")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days
REFRESH_TOKEN_EXPIRE_DAYS = 30  # 30 days

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    logger.debug(f"Access token created for {data.get('sub', '[no sub]')} expiring at {expire}")
    return token

def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire, "type": "refresh", "jti": secrets.token_hex(16)})
    token = jwt.encode(to_encode, REFRESH_SECRET_KEY, algorithm=ALGORITHM)
    logger.debug(f"Refresh token created for {data.get('sub', '[no sub]')} expiring at {expire}")
    return token

def create_token_pair(user_id: str) -> Tuple[str, str]:
    data = {"sub": user_id}
    access_token = create_access_token(data)
    refresh_token = create_refresh_token(data)
    return access_token, refresh_token

def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        logger.debug(f"Token successfully decoded: {payload}")
        return payload
    except JWTError as e:
        logger.warning(f"Failed to decode JWT: {e}")
        return None

def decode_refresh_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, REFRESH_SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            logger.warning("Token is not a refresh token")
            return None
        logger.debug(f"Refresh token successfully decoded: {payload}")
        return payload
    except JWTError as e:
        logger.warning(f"Failed to decode refresh JWT: {e}")
        return None
