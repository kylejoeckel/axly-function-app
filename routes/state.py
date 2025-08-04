"""
Small module that keeps global, in‑memory dictionaries.

Import *only* from Functions that really need them; this avoids
circular‑import headaches.
"""

# history kept between invocations until the worker is recycled
CONVERSATIONS: dict[str, list[dict]] = {}

# vehicle metadata staging area when the client has not yet stored a Vehicle row
CAR_META: dict[str, dict] = {}
