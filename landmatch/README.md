# LandMatch

A land marketplace for Tamil Nadu that matches sellers with buyers. Sellers post land with photos and ownership documents; every listing is risk-scored for fraud; buyers save requirements and get ranked matches, or just speak a search.

## Features

- **Roles:** buyer, seller, admin (JWT login, PBKDF2 password hashing)
- **Listings:** photos, ownership documents, coordinates with map, cents / acres / sq ft units, INR pricing
- **Matching:** each buyer requirement scores every live listing 0-100 (district, land type, budget, area, keywords) and explains why
- **Voice + natural-language search:** "2 acres agricultural land in Tiruppur under 60 lakhs" works in English, and Tamil words (ஏக்கர், சென்ட், லட்சம், கோடி) are understood. Speech input uses the browser's Web Speech API (Chrome / Edge / Android) with English, Tamil and Hindi
- **Fraud detection (rule based):** duplicate survey numbers, price far from district median, missing documents or photos, scam phrases, contact details in descriptions, listing bursts, coordinates outside India, brand-new high-value sellers
- **Admin review desk:** risk-sorted queue, view documents, approve / reject with a note, suspend users
- **Privacy:** ownership documents are never publicly served (owner + admin only); seller phone is shown only to logged-in users

## Run it

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd backend
uvicorn main:app --reload
```

Open http://localhost:8000 (site) or http://localhost:8000/docs (API explorer).

A default admin is created on first start: `admin@landmatch.local` / `Admin@123`.
Override with env vars `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and set `SECRET_KEY` to a long random string before deploying.

Optional env vars: `DATABASE_URL` (default SQLite file `landmatch.db`), `UPLOADS_DIR`, `CORS_ORIGINS`.

## Tests

```bash
pip install pytest
python -m pytest -q tests
```

## How listings are moderated

| Risk score | Result |
|---|---|
| under 30 and has documents | Approved automatically |
| 30 and above, or no documents | Pending admin review |
| 60 and above | Pending, shown as high risk at the top of the queue |

Rules live in `backend/fraud_detection.py`; weights and thresholds are constants at the top of the file. The score prioritises human review. It does not verify ownership. Admins should compare the uploaded patta / chitta / EC with the official Tamil Nilam records.

## Structure

```
backend/   FastAPI app: main, database, models, schemas, auth, matching, fraud_detection, routers/
frontend/  Static pages and JS (served by FastAPI at /)
uploads/   images/ (public) and documents/ (private)
tests/     End-to-end API smoke tests
```

## Before going to production

- Set a strong `SECRET_KEY` and change the admin password
- Restrict `CORS_ORIGINS`, serve behind HTTPS
- Move to PostgreSQL and add Alembic migrations
- Store uploads in object storage (S3 / GCS) with virus scanning
- Add rate limiting on login / register and email or OTP verification for phone numbers
- Pre-filter matches in SQL instead of scoring every listing in Python
