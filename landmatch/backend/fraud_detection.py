"""Rule-based fraud / risk scoring for new land listings (0 = clean, 100 = very risky).

These are heuristics to help admins prioritise review; they never replace verifying the
original documents (patta, chitta, EC, FMB sketch) against government records.
"""
import json
import re
import statistics
from datetime import timedelta
from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from models import Land, utcnow

SUSPICIOUS_PHRASES = [
    "advance payment", "send money", "western union", "token amount before", "urgent sale",
    "no verification", "whatsapp only", "gift card", "100% guarantee", "cheapest ever",
    "owner abroad", "owner is abroad", "pay before visit", "booking amount online",
]
PHONE_RE = re.compile(r"(?:\+?91[\s-]?)?[6-9]\d{9}")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")

AUTO_APPROVE_BELOW = 30
HIGH_RISK_FROM = 60


def risk_level(score: int) -> str:
    return "high" if score >= HIGH_RISK_FROM else "medium" if score >= AUTO_APPROVE_BELOW else "low"


def decide_status(score: int, doc_count: int) -> str:
    """Low-risk listings that include documents go live immediately; the rest wait for an admin."""
    return "approved" if score < AUTO_APPROVE_BELOW and doc_count > 0 else "pending"


def analyze_listing(
    db: Session, *, seller: models.User, title: str, description: str, district: str,
    land_type: str, area_sqft: float, price: float, survey_number: str,
    latitude: Optional[float], longitude: Optional[float], image_count: int, doc_count: int,
) -> Tuple[int, List[str]]:
    score, flags = 0, []

    def add(points: int, message: str):
        nonlocal score
        score += points
        flags.append(message)

    # 1. Duplicate survey number in the same district
    if survey_number:
        dupes = (db.query(Land)
                 .filter(func.lower(Land.survey_number) == survey_number.lower(),
                         func.lower(Land.district) == district.lower(),
                         Land.status.in_(("pending", "approved")))
                 .all())
        if any(d.seller_id != seller.id for d in dupes):
            add(50, "Same survey number is listed by a different seller")
        elif dupes:
            add(20, "This seller already listed the same survey number")
    else:
        add(10, "No survey number provided")

    # 2. Price per sq ft vs comparable listings
    comps = (db.query(Land.price, Land.area_sqft)
             .filter(Land.status.in_(("approved", "sold")),
                     func.lower(Land.district) == district.lower(),
                     Land.land_type == land_type, Land.area_sqft > 0)
             .all())
    if len(comps) >= 3 and area_sqft > 0:
        median = statistics.median(p / a for p, a in comps)
        ratio = (price / area_sqft) / median if median else 1
        if ratio < 0.3:
            add(35, f"Price per sq ft is {ratio:.0%} of the {district} median (too good to be true)")
        elif ratio > 3:
            add(20, f"Price per sq ft is {ratio:.1f}x the {district} median")

    # 3. Evidence
    if doc_count == 0:
        add(20, "No ownership documents uploaded")
    if image_count == 0:
        add(10, "No photos uploaded")

    # 4. Scam language and contact leakage
    text = f"{title} {description}".lower()
    hits = [p for p in SUSPICIOUS_PHRASES if p in text]
    if hits:
        add(min(30, 15 * len(hits)), "Suspicious wording: " + ", ".join(hits))
    if PHONE_RE.search(description or "") or EMAIL_RE.search(description or ""):
        add(10, "Contact details placed in the description")

    # 5. Sanity checks
    if area_sqft <= 0 or price <= 0:
        add(40, "Area or price is zero or negative")
    if latitude is not None and longitude is not None and not (6 <= latitude <= 38 and 68 <= longitude <= 98):
        add(30, "Coordinates are outside India")

    # 6. Seller behaviour
    since = utcnow() - timedelta(hours=24)
    recent = db.query(func.count(Land.id)).filter(Land.seller_id == seller.id, Land.created_at >= since).scalar() or 0
    if recent >= 5:
        add(25, f"{recent} listings posted by this seller in 24 hours")
    if seller.created_at and utcnow() - seller.created_at < timedelta(days=1) and price >= 1e7:
        add(15, "Brand-new account listing land worth over 1 crore")

    return min(score, 100), flags


def dump_flags(flags: List[str]) -> str:
    return json.dumps(flags)
