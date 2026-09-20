from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import models
import schemas
from auth import get_optional_user, require_role
from database import get_db
from matching import LAND_TYPES, MIN_MATCH_SCORE, parse_voice_query, score_match
from routers.lands import build_search_query, serialize_land

router = APIRouter()


@router.post("/requirements", response_model=schemas.RequirementOut, status_code=201)
def create_requirement(payload: schemas.RequirementCreate, db: Session = Depends(get_db),
                       buyer: models.User = Depends(require_role("buyer"))):
    if payload.land_type and payload.land_type not in LAND_TYPES:
        raise HTTPException(400, f"land_type must be one of: {', '.join(LAND_TYPES)}")
    for lo, hi, label in ((payload.min_price, payload.max_price, "price"), (payload.min_area_sqft, payload.max_area_sqft, "area")):
        if lo is not None and hi is not None and lo > hi:
            raise HTTPException(400, f"Minimum {label} cannot be higher than maximum {label}.")
    if not any([payload.district, payload.land_type, payload.min_price, payload.max_price,
                payload.min_area_sqft, payload.max_area_sqft, payload.keywords]):
        raise HTTPException(400, "Add at least one thing you are looking for.")
    req = models.BuyerRequirement(buyer_id=buyer.id, **payload.model_dump())
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


@router.get("/requirements", response_model=List[schemas.RequirementOut])
def my_requirements(db: Session = Depends(get_db), buyer: models.User = Depends(require_role("buyer"))):
    return (db.query(models.BuyerRequirement).filter(models.BuyerRequirement.buyer_id == buyer.id)
            .order_by(models.BuyerRequirement.created_at.desc()).all())


@router.delete("/requirements/{req_id}", status_code=204)
def delete_requirement(req_id: int, db: Session = Depends(get_db), buyer: models.User = Depends(require_role("buyer"))):
    req = db.get(models.BuyerRequirement, req_id)
    if not req or req.buyer_id != buyer.id:
        raise HTTPException(404, "Requirement not found.")
    db.delete(req)
    db.commit()


@router.get("/requirements/{req_id}/matches", response_model=List[schemas.MatchOut], response_model_exclude_none=True)
def requirement_matches(req_id: int, limit: int = Query(20, ge=1, le=50), db: Session = Depends(get_db),
                        buyer: models.User = Depends(require_role("buyer"))):
    req = db.get(models.BuyerRequirement, req_id)
    if not req or req.buyer_id != buyer.id:
        raise HTTPException(404, "Requirement not found.")
    # MVP: score every approved listing in Python. For large datasets, pre-filter by district/type in SQL.
    lands = db.query(models.Land).filter(models.Land.status == "approved").all()
    scored = []
    for land in lands:
        score, reasons = score_match(land, req)
        if score >= MIN_MATCH_SCORE:
            scored.append({"land": serialize_land(land, show_contact=True), "score": score, "reasons": reasons})
    scored.sort(key=lambda m: m["score"], reverse=True)
    return scored[:limit]


@router.get("/voice-search")
def voice_search(q: str = Query(..., min_length=2, max_length=300), limit: int = Query(20, ge=1, le=50),
                 db: Session = Depends(get_db), user: Optional[models.User] = Depends(get_optional_user)):
    """Turn a spoken/typed sentence into filters and return matching approved listings."""
    parsed = parse_voice_query(q)
    lands = (build_search_query(db, **parsed).order_by(models.Land.created_at.desc()).limit(limit).all())
    return {"query": q, "parsed": parsed, "results": [serialize_land(l, show_contact=bool(user)) for l in lands]}
