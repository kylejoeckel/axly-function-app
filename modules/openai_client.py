# services/openai_client.py
import os
from functools import lru_cache
from openai import OpenAI

@lru_cache(maxsize=1)
def client() -> OpenAI:
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
