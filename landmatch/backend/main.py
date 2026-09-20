import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import models
from auth import hash_password
from database import BASE_DIR, IMAGE_DIR, SessionLocal, engine, Base
from routers import buyers, lands, users

FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@landmatch.local")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin@123")

Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db = SessionLocal()
    try:
        if not db.query(models.User).filter(models.User.role == "admin").first():
            db.add(models.User(name="LandMatch Admin", email=ADMIN_EMAIL, phone="9000000000",
                               password_hash=hash_password(ADMIN_PASSWORD), role="admin"))
            db.commit()
            print(f"[LandMatch] Created admin account {ADMIN_EMAIL} - change the password before deploying.")
    finally:
        db.close()
    yield


app = FastAPI(title="LandMatch API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])

app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(lands.router, prefix="/api/lands", tags=["lands"])
app.include_router(buyers.router, prefix="/api/buyers", tags=["buyers"])


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Only photos are public. Ownership documents are served by /api/lands/documents/{id} (owner/admin only).
app.mount("/uploads/images", StaticFiles(directory=IMAGE_DIR), name="images")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
