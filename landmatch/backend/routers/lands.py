import json
import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import models
import schemas
from auth import get_current_user, get_optional_user, require_role
from database import DOC_DIR, IMAGE_DIR, get_db
from fraud_detection import analyze_listing, decide_status, dump_flags
from matching import LAND_TYPES, MIN_MATCH_SCORE, TN_DISTRICTS, score_match

router = APIRouter()

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
DOC_EXT = {".pdf", ".jpg", ".jpeg", ".png"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_DOC_BYTES = 10 * 1024 * 1024
MAX_IMAGES, MAX_DOCS = 8, 5


# --------------------------------------------------------------------------- helpers
def serialize_land(land: models.Land, level: str = "public", show_contact: bool = False) -> dict:
    """level: public | owner | admin. Sensitive fields are added only for higher levels."""
    d = {
        "id": land.id, "title": land.title, "description": land.description or "",
        "land_type": land.land_type, "district": land.district, "village": land.village or "",
        "address": land.address or "", "latitude": land.latitude, "longitude": land.longitude,
        "area_sqft": land.area_sqft, "price": land.price,
        "price_per_sqft": round(land.price / land.area_sqft) if land.area_sqft else None,
        "status": land.status, "created_at": land.created_at,
        "images": [{"id": i.id, "url": i.url} for i in land.images],
        "document_count": len(land.documents),
        "seller_name": land.seller.name if land.seller else None,
    }
    if show_contact and land.seller:
        d["seller_phone"] = land.seller.phone
    if level in ("owner", "admin"):
        d["survey_number"] = land.survey_number or ""
        d["admin_note"] = land.admin_note or ""
        d["documents"] = [{"id": x.id, "name": x.original_name or x.filename} for x in land.documents]
    if level == "admin":
        d["fraud_score"] = land.fraud_score
        d["fraud_flags"] = json.loads(land.fraud_flags or "[]")
        d["seller_email"] = land.seller.email if land.seller else None
    return d


def build_search_query(db: Session, district=None, land_type=None, min_price=None, max_price=None,
                       min_area=None, max_area=None, q=None):
    query = db.query(models.Land).filter(models.Land.status == "approved")
    if district:
        query = query.filter(func.lower(models.Land.district) == district.lower())
    if land_type:
        query = query.filter(models.Land.land_type == land_type)
    if min_price is not None:
        query = query.filter(models.Land.price >= min_price)
    if max_price is not None:
        query = query.filter(models.Land.price <= max_price)
    if min_area is not None:
        query = query.filter(models.Land.area_sqft >= min_area)
    if max_area is not None:
        query = query.filter(models.Land.area_sqft <= max_area)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(models.Land.title.ilike(like), models.Land.description.ilike(like),
                                 models.Land.village.ilike(like), models.Land.district.ilike(like),
                                 models.Land.address.ilike(like)))
    return query


async def save_upload(file: UploadFile, folder: str, allowed: set, max_bytes: int) -> str:
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(400, f"'{file.filename}' is not allowed. Use: {', '.join(sorted(allowed))}")
    data = await file.read()
    if not data:
        raise HTTPException(400, f"'{file.filename}' is empty.")
    if len(data) > max_bytes:
        raise HTTPException(400, f"'{file.filename}' is larger than {max_bytes // (1024 * 1024)} MB.")
    name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(folder, name), "wb") as fh:
        fh.write(data)
    return name


def _remove_files(land: models.Land):
    for img in land.images:
        _silent_remove(os.path.join(IMAGE_DIR, img.filename))
    for doc in land.documents:
        _silent_remove(os.path.join(DOC_DIR, doc.filename))


def _silent_remove(path: str):
    try:
        os.remove(path)
    except OSError:
        pass


def _level(user: Optional[models.User], land: models.Land) -> str:
    if user and user.role == "admin":
        return "admin"
    if user and user.id == land.seller_id:
        return "owner"
    return "public"


# --------------------------------------------------------------------------- public
@router.get("/meta/options")
def options():
    return {"districts": TN_DISTRICTS, "land_types": LAND_TYPES}


@router.get("", response_model=List[schemas.LandOut], response_model_exclude_none=True)
def search_lands(
    district: Optional[str] = None, land_type: Optional[str] = None,
    min_price: Optional[float] = None, max_price: Optional[float] = None,
    min_area: Optional[float] = None, max_area: Optional[float] = None,
    q: Optional[str] = None, sort: str = "newest",
    page: int = Query(1, ge=1), limit: int = Query(12, ge=1, le=50),
    db: Session = Depends(get_db), user: Optional[models.User] = Depends(get_optional_user),
):
    query = build_search_query(db, district, land_type, min_price, max_price, min_area, max_area, q)
    order = {"price_asc": models.Land.price.asc(), "price_desc": models.Land.price.desc(),
             "area_desc": models.Land.area_sqft.desc()}.get(sort, models.Land.created_at.desc())
    lands = query.order_by(order).offset((page - 1) * limit).limit(limit).all()
    return [serialize_land(l, show_contact=bool(user)) for l in lands]


# --------------------------------------------------------------------------- seller
@router.post("", response_model=schemas.LandOut, response_model_exclude_none=True, status_code=201)
async def create_land(
    title: str = Form(..., min_length=5, max_length=200),
    land_type: str = Form(...), district: str = Form(..., min_length=2),
    area_sqft: float = Form(..., gt=0), price: float = Form(..., gt=0),
    description: str = Form("", max_length=5000), village: str = Form("", max_length=100),
    address: str = Form("", max_length=255), survey_number: str = Form("", max_length=60),
    latitude: Optional[float] = Form(None), longitude: Optional[float] = Form(None),
    images: List[UploadFile] = File(default=[]), documents: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db), seller: models.User = Depends(require_role("seller")),
):
    if land_type not in LAND_TYPES:
        raise HTTPException(400, f"land_type must be one of: {', '.join(LAND_TYPES)}")
    images = [f for f in images if f.filename]
    documents = [f for f in documents if f.filename]
    if len(images) > MAX_IMAGES or len(documents) > MAX_DOCS:
        raise HTTPException(400, f"Upload at most {MAX_IMAGES} photos and {MAX_DOCS} documents.")

    saved_images = [(await save_upload(f, IMAGE_DIR, IMAGE_EXT, MAX_IMAGE_BYTES)) for f in images]
    saved_docs = [((await save_upload(f, DOC_DIR, DOC_EXT, MAX_DOC_BYTES)), f.filename) for f in documents]

    score, flags = analyze_listing(
        db, seller=seller, title=title, description=description, district=district,
        land_type=land_type, area_sqft=area_sqft, price=price, survey_number=survey_number.strip(),
        latitude=latitude, longitude=longitude, image_count=len(saved_images), doc_count=len(saved_docs),
    )
    land = models.Land(
        seller_id=seller.id, title=title.strip(), description=description, land_type=land_type,
        district=district.strip(), village=village.strip(), address=address.strip(),
        latitude=latitude, longitude=longitude, area_sqft=area_sqft, price=price,
        survey_number=survey_number.strip(), fraud_score=score, fraud_flags=dump_flags(flags),
        status=decide_status(score, len(saved_docs)),
    )
    land.images = [models.LandImage(filename=n, url=f"/uploads/images/{n}") for n in saved_images]
    land.documents = [models.LandDocument(filename=n, original_name=o) for n, o in saved_docs]
    db.add(land)
    db.commit()
    db.refresh(land)
    return serialize_land(land, "owner")


@router.get("/mine", response_model=List[schemas.LandOut], response_model_exclude_none=True)
def my_lands(db: Session = Depends(get_db), seller: models.User = Depends(require_role("seller"))):
    lands = db.query(models.Land).filter(models.Land.seller_id == seller.id).order_by(models.Land.created_at.desc()).all()
    return [serialize_land(l, "owner") for l in lands]


# --------------------------------------------------------------------------- admin
@router.get("/admin/stats")
def admin_stats(db: Session = Depends(get_db), _: models.User = Depends(require_role("admin"))):
    by_status = dict(db.query(models.Land.status, func.count(models.Land.id)).group_by(models.Land.status).all())
    return {
        "lands": {s: by_status.get(s, 0) for s in ("pending", "approved", "rejected", "sold")},
        "users": db.query(func.count(models.User.id)).scalar(),
        "requirements": db.query(func.count(models.BuyerRequirement.id)).scalar(),
        "high_risk_pending": db.query(func.count(models.Land.id))
                               .filter(models.Land.status == "pending", models.Land.fraud_score >= 60).scalar(),
    }


@router.get("/admin/list", response_model=List[schemas.LandOut], response_model_exclude_none=True)
def admin_list(status: Optional[str] = None, db: Session = Depends(get_db),
               _: models.User = Depends(require_role("admin"))):
    query = db.query(models.Land)
    if status:
        query = query.filter(models.Land.status == status)
    lands = query.order_by(models.Land.fraud_score.desc(), models.Land.created_at.desc()).limit(200).all()
    return [serialize_land(l, "admin", show_contact=True) for l in lands]


@router.post("/admin/{land_id}/review", response_model=schemas.LandOut, response_model_exclude_none=True)
def admin_review(land_id: int, payload: schemas.ReviewIn, db: Session = Depends(get_db),
                 _: models.User = Depends(require_role("admin"))):
    land = db.get(models.Land, land_id)
    if not land:
        raise HTTPException(404, "Listing not found.")
    land.status = "approved" if payload.action == "approve" else "rejected"
    land.admin_note = payload.note or ""
    db.commit()
    db.refresh(land)
    return serialize_land(land, "admin", show_contact=True)


# --------------------------------------------------------------------------- documents (owner/admin only)
@router.get("/documents/{doc_id}")
def download_document(doc_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    doc = db.get(models.LandDocument, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found.")
    if user.role != "admin" and doc.land.seller_id != user.id:
        raise HTTPException(403, "Only the owner or an admin can view documents.")
    path = os.path.join(DOC_DIR, doc.filename)
    if not os.path.exists(path):
        raise HTTPException(404, "File is missing on the server.")
    return FileResponse(path, filename=doc.original_name or doc.filename)


# --------------------------------------------------------------------------- single listing
@router.get("/{land_id}", response_model=schemas.LandOut, response_model_exclude_none=True)
def get_land(land_id: int, db: Session = Depends(get_db), user: Optional[models.User] = Depends(get_optional_user)):
    land = db.get(models.Land, land_id)
    if not land:
        raise HTTPException(404, "Listing not found.")
    level = _level(user, land)
    if land.status not in ("approved", "sold") and level == "public":
        raise HTTPException(404, "Listing not found.")
    return serialize_land(land, level, show_contact=bool(user))


@router.get("/{land_id}/demand")
def land_demand(land_id: int, db: Session = Depends(get_db), seller: models.User = Depends(require_role("seller"))):
    """How many buyer requirements match this listing (anonymous count)."""
    land = db.get(models.Land, land_id)
    if not land or land.seller_id != seller.id:
        raise HTTPException(404, "Listing not found.")
    scores = [score_match(land, r)[0] for r in db.query(models.BuyerRequirement).all()]
    matched = [s for s in scores if s >= MIN_MATCH_SCORE]
    return {"interested_buyers": len(matched), "best_score": max(matched) if matched else 0}


@router.post("/{land_id}/sold", response_model=schemas.LandOut, response_model_exclude_none=True)
def mark_sold(land_id: int, db: Session = Depends(get_db), seller: models.User = Depends(require_role("seller"))):
    land = db.get(models.Land, land_id)
    if not land or land.seller_id != seller.id:
        raise HTTPException(404, "Listing not found.")
    land.status = "sold"
    db.commit()
    db.refresh(land)
    return serialize_land(land, "owner")


@router.delete("/{land_id}", status_code=204)
def delete_land(land_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    land = db.get(models.Land, land_id)
    if not land or (user.role != "admin" and land.seller_id != user.id):
        raise HTTPException(404, "Listing not found.")
    _remove_files(land)
    db.delete(land)
    db.commit()
