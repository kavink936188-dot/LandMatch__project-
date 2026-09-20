import os, sys, tempfile
tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/t.db"
os.environ["UPLOADS_DIR"] = f"{tmp}/uploads"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from fastapi.testclient import TestClient
from main import app
from matching import parse_voice_query


def reg(c, name, email, role):
    r = c.post("/api/users/register", json={"name": name, "email": email, "phone": "9876543210", "password": "secret123", "role": role})
    assert r.status_code == 201, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def test_flow():
    with TestClient(app) as c:
        seller, buyer = reg(c, "Seller One", "s@x.com", "seller"), reg(c, "Buyer One", "b@x.com", "buyer")
        adm = c.post("/api/users/login", data={"username": "admin@landmatch.local", "password": "Admin@123"}).json()
        adm = {"Authorization": "Bearer " + adm["access_token"]}

        files = [("images", ("a.jpg", b"\xff\xd8\xff fake", "image/jpeg")), ("documents", ("patta.pdf", b"%PDF-1.4 x", "application/pdf"))]
        form = dict(title="2 acre coconut farm near Udumalpet", land_type="agricultural", district="Tiruppur",
                    area_sqft=87120, price=4500000, survey_number="123/4A", village="Kolumam")
        r = c.post("/api/lands", data=form, files=files, headers=seller)
        assert r.status_code == 201, r.text
        land = r.json()
        assert land["status"] == "approved" and "fraud_score" not in land, land

        # duplicate survey number by another seller -> flagged, pending
        seller2 = reg(c, "Seller Two", "s2@x.com", "seller")
        r = c.post("/api/lands", data={**form, "title": "Same plot cheaper urgent sale"}, headers=seller2)
        dup = r.json()
        assert dup["status"] == "pending", dup
        a = c.get("/api/lands/admin/list?status=pending", headers=adm).json()
        assert a[0]["fraud_score"] >= 50 and a[0]["fraud_flags"], a
        assert c.post(f"/api/lands/admin/{dup['id']}/review", json={"action": "reject", "note": "dup"}, headers=adm).json()["status"] == "rejected"

        # public search never shows pending; contact hidden when anonymous
        res = c.get("/api/lands", params={"district": "Tiruppur"}).json()
        assert len(res) == 1 and "seller_phone" not in res[0]
        assert "seller_phone" in c.get("/api/lands", headers=buyer).json()[0]
        assert c.get(f"/api/lands/{dup['id']}").status_code == 404

        # docs private
        doc_id = c.get(f"/api/lands/{land['id']}", headers=seller).json()["documents"][0]["id"]
        assert c.get(f"/api/lands/documents/{doc_id}", headers=seller).status_code == 200
        assert c.get(f"/api/lands/documents/{doc_id}", headers=buyer).status_code == 403
        assert c.get(f"/uploads/documents/x").status_code in (404,)

        # requirement + matches
        req = c.post("/api/buyers/requirements", json={"district": "Tiruppur", "land_type": "agricultural", "max_price": 5000000, "min_area_sqft": 40000}, headers=buyer)
        assert req.status_code == 201, req.text
        m = c.get(f"/api/buyers/requirements/{req.json()['id']}/matches", headers=buyer).json()
        assert m and m[0]["score"] == 100, m
        assert c.get(f"/api/lands/{land['id']}/demand", headers=seller).json()["interested_buyers"] == 1

        # role guards
        assert c.post("/api/lands", data=form, headers=buyer).status_code == 403
        assert c.get("/api/lands/admin/stats", headers=seller).status_code == 403
        assert c.get("/api/lands/admin/stats", headers=adm).json()["lands"]["approved"] == 1

        v = c.get("/api/buyers/voice-search", params={"q": "2 acres agricultural land in Tirupur under 60 lakhs"}).json()
        assert v["parsed"]["district"] == "Tiruppur" and len(v["results"]) == 1, v


def test_parser():
    p = parse_voice_query("plot above 10 lakhs in Coimbatore")
    assert p["min_price"] == 1e6 and p["district"] == "Coimbatore" and p["land_type"] == "residential"
    p = parse_voice_query("5 cents house site below 1.5 crore")
    assert round(p["min_area"]) == round(5 * 435.6 * .75) and p["max_price"] == 1.5e7
    assert "q" in parse_voice_query("something nice")
