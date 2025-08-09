# seeds/services_library_seed.py
from models.service import ServicesLibrary
from sqlalchemy.orm import Session

DEFAULTS = [
    dict(name="Oil Change", category="Engine", description="Engine oil & filter", default_interval_miles=5000, default_interval_months=6),
    dict(name="Tire Rotation", category="Tires", description="Rotate tires", default_interval_miles=6000, default_interval_months=6),
    dict(name="Brake Inspection", category="Brakes", description="Inspect pads/rotors", default_interval_months=12),
    dict(name="Cabin Air Filter", category="Filters", description="Replace cabin filter", default_interval_miles=15000, default_interval_months=18),
]

def seed_services_library(session: Session):
    existing = {s.name for s in session.query(ServicesLibrary).all()}
    for row in DEFAULTS:
        if row["name"] in existing:
            continue
        session.add(ServicesLibrary(**row))
    session.commit()
