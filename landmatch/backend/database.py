import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOADS_DIR = os.getenv("UPLOADS_DIR", os.path.join(BASE_DIR, "uploads"))
IMAGE_DIR = os.path.join(UPLOADS_DIR, "images")
DOC_DIR = os.path.join(UPLOADS_DIR, "documents")
for _d in (IMAGE_DIR, DOC_DIR):
    os.makedirs(_d, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'landmatch.db')}")
_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
