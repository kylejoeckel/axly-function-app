# db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DEFAULT_LOCAL = "postgresql+psycopg2://axly_user:axly_pass@localhost:5432/axly"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_LOCAL)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "2")),
    pool_recycle=1800,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
