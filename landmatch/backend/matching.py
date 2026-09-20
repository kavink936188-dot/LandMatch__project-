"""Buyer <-> land matching and natural-language (voice) query parsing."""
import re
from typing import Dict, List, Optional, Tuple

ACRE_SQFT = 43560.0
CENT_SQFT = 435.6

LAND_TYPES = ["agricultural", "residential", "commercial", "industrial"]

TN_DISTRICTS = [
    "Ariyalur", "Chengalpattu", "Chennai", "Coimbatore", "Cuddalore", "Dharmapuri", "Dindigul",
    "Erode", "Kallakurichi", "Kancheepuram", "Kanniyakumari", "Karur", "Krishnagiri", "Madurai",
    "Mayiladuthurai", "Nagapattinam", "Namakkal", "Nilgiris", "Perambalur", "Pudukkottai",
    "Ramanathapuram", "Ranipet", "Salem", "Sivagangai", "Tenkasi", "Thanjavur", "Theni",
    "Thiruvallur", "Thiruvarur", "Thoothukudi", "Tiruchirappalli", "Tirunelveli", "Tirupathur",
    "Tiruppur", "Tiruvannamalai", "Vellore", "Viluppuram", "Virudhunagar",
]

DISTRICT_ALIASES = {
    "tirupur": "Tiruppur", "kovai": "Coimbatore", "trichy": "Tiruchirappalli",
    "tuticorin": "Thoothukudi", "nellai": "Tirunelveli", "kanyakumari": "Kanniyakumari",
    "kanchipuram": "Kancheepuram", "tiruvallur": "Thiruvallur", "villupuram": "Viluppuram",
    "ooty": "Nilgiris", "tanjore": "Thanjavur",
}

TYPE_WORDS = {
    "agricultural": ["agricultural", "agriculture", "farm", "farmland", "paddy", "coconut", "விவசாய", "வயல்", "தோட்டம்"],
    "residential": ["residential", "house site", "housing", "plot", "layout", "dtcp", "வீட்டு மனை", "மனை"],
    "commercial": ["commercial", "shop", "showroom", "business", "வணிக"],
    "industrial": ["industrial", "factory", "godown", "warehouse", "தொழிற்சாலை"],
}

WEIGHTS = {"district": 25, "land_type": 20, "price": 25, "area": 20, "keywords": 10}
MIN_MATCH_SCORE = 40


# --------------------------------------------------------------------------- scoring
def _range_score(value: float, lo: Optional[float], hi: Optional[float], tolerance: float = 0.15):
    """1.0 inside [lo, hi]; decays linearly to 0 at `tolerance` outside the range."""
    if lo is not None and value < lo:
        gap = (lo - value) / lo if lo > 0 else 1.0
        return max(0.0, 1 - gap / tolerance), "below"
    if hi is not None and hi > 0 and value > hi:
        gap = (value - hi) / hi
        return max(0.0, 1 - gap / tolerance), "above"
    return 1.0, "inside"


def score_match(land, req) -> Tuple[int, List[str]]:
    """Score 0-100 for how well `land` fits buyer requirement `req`, plus human-readable reasons."""
    earned, possible, reasons = 0.0, 0.0, []
    penalty = 1.0

    if req.district:
        possible += WEIGHTS["district"]
        if land.district.lower() == req.district.lower():
            earned += WEIGHTS["district"]
            reasons.append(f"In {land.district}")
        else:
            penalty *= 0.4
            reasons.append(f"Different district ({land.district})")

    if req.land_type:
        possible += WEIGHTS["land_type"]
        if land.land_type == req.land_type:
            earned += WEIGHTS["land_type"]
            reasons.append(f"{land.land_type.title()} land")
        else:
            penalty *= 0.4
            reasons.append(f"Different land type ({land.land_type})")

    if req.min_price is not None or req.max_price is not None:
        possible += WEIGHTS["price"]
        s, where = _range_score(land.price, req.min_price, req.max_price)
        earned += WEIGHTS["price"] * s
        reasons.append({"inside": "Within budget", "above": "Slightly above budget", "below": "Below your price range"}[where]
                       if s > 0 else "Outside budget")

    if req.min_area_sqft is not None or req.max_area_sqft is not None:
        possible += WEIGHTS["area"]
        s, where = _range_score(land.area_sqft, req.min_area_sqft, req.max_area_sqft)
        earned += WEIGHTS["area"] * s
        reasons.append({"inside": "Area fits", "above": "Slightly larger than wanted", "below": "Slightly smaller than wanted"}[where]
                       if s > 0 else "Area outside your range")

    if req.keywords:
        tokens = [t for t in re.split(r"[,\s]+", req.keywords.lower()) if len(t) > 2]
        if tokens:
            possible += WEIGHTS["keywords"]
            haystack = " ".join([land.title, land.description or "", land.village or "", land.address or ""]).lower()
            hits = [t for t in tokens if t in haystack]
            earned += WEIGHTS["keywords"] * len(hits) / len(tokens)
            if hits:
                reasons.append("Mentions " + ", ".join(hits))

    if possible == 0:
        return 50, ["No specific criteria set"]
    return round(earned / possible * 100 * penalty), reasons


# --------------------------------------------------------------------------- voice / NL parsing
_AREA_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(acres?|cents?|sq\.?\s*ft|sqft|square\s*feet|ஏக்கர்|சென்ட்)(?![a-zA-Z])", re.I)
_PRICE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(crores?|cr|lakhs?|lacs?|thousand|k|கோடி|லட்சம்)(?![a-zA-Z])", re.I)
_MAX_WORDS = ("under", "below", "less than", "within", "upto", "up to", "max", "maximum", "budget", "at most", "cheaper than")
_MIN_WORDS = ("above", "over", "more than", "min", "minimum", "at least", "starting")


def _qualifier(text: str, start: int) -> Optional[str]:
    before = text[max(0, start - 22):start].lower()
    if any(w in before for w in _MAX_WORDS):
        return "max"
    if any(w in before for w in _MIN_WORDS):
        return "min"
    return None


def _area_to_sqft(n: float, unit: str) -> float:
    u = unit.lower()
    if u.startswith("acre") or u == "ஏக்கர்":
        return n * ACRE_SQFT
    if u.startswith("cent") or u == "சென்ட்":
        return n * CENT_SQFT
    return n


def _price_to_inr(n: float, unit: str) -> float:
    u = unit.lower()
    if u.startswith("cr") or u == "கோடி":
        return n * 1e7
    if u.startswith(("lakh", "lac")) or u == "லட்சம்":
        return n * 1e5
    return n * 1e3


def parse_voice_query(text: str) -> Dict:
    """'2 acres agricultural land in Tiruppur under 50 lakhs' -> filter dict."""
    out: Dict = {}
    lower = text.lower()

    for alias, name in DISTRICT_ALIASES.items():
        if alias in lower:
            out["district"] = name
    for name in TN_DISTRICTS:
        if name.lower() in lower:
            out["district"] = name

    for land_type, words in TYPE_WORDS.items():
        if any(w in lower for w in words):
            out["land_type"] = land_type
            break

    m = _AREA_RE.search(text)
    if m:
        sqft = _area_to_sqft(float(m.group(1)), m.group(2))
        q = _qualifier(text, m.start())
        if q == "max":
            out["max_area"] = sqft
        elif q == "min":
            out["min_area"] = sqft
        else:  # "2 acres" -> roughly 2 acres
            out["min_area"], out["max_area"] = sqft * 0.75, sqft * 1.25

    # remove the area match so "5 cents" isn't read as a price unit
    price_text = text[:m.start()] + " " * (m.end() - m.start()) + text[m.end():] if m else text
    p = _PRICE_RE.search(price_text)
    if p:
        inr = _price_to_inr(float(p.group(1)), p.group(2))
        q = _qualifier(price_text, p.start())
        if q == "min":
            out["min_price"] = inr
        else:  # default reading of a price is a budget ceiling
            out["max_price"] = inr

    if not out:
        out["q"] = text.strip()
    return out
