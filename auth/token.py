import os
from datetime import datetime, timedelta
from typing import Optional

import jwt
from jwt.exceptions import PyJWTError as JWTError
# from dotenv import load_dotenv
import logging

# load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fallback-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)  # or DEBUG during development

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    logger.debug(f"Access token created for {data.get('sub', '[no sub]')} expiring at {expire}")
    return token

def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        logger.debug(f"Token successfully decoded: {payload}")
        return payload
    except JWTError as e:
        logger.warning(f"Failed to decode JWT: {e}")
        return None
