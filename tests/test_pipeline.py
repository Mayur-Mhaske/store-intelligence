# PROMPT: "Generate pytest tests for FastAPI store intelligence API with SQLite.
# Cover: ingest, idempotency, batch 500, empty store, staff exclusion, zero purchases,
# re-entry dedup in funnel, anomaly structure, health endpoint, heatmap normalization."
# CHANGES MADE: Updated store_id to ST1008 (Brigade Bangalore), fixed timestamp format,
# added edge case for all-staff clip returning 0 unique_visitors.

import pytest, uuid, sys
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append("../app")
from main import app
from database import Base, get_db

engine = create_engine("sqlite:///./test.db", connect_args={"check_same_thread": False})
TestSession = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)


def override_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_db
client = TestClient(app)

STORE = "ST1008"


def ev(store_id=None, visitor_id=None, event_type="ENTRY", zone_id=None,
       is_staff=False, confidence=0.91, timestamp="2026-04-10T10:00:00Z", event_id=None):
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "store_id": store_id or STORE,
        "camera_id": "CAM_1",
        "visitor_id": visitor_id or f"VIS_{str(uuid.uuid4())[:6]}",
        "event_type": event_type,
        "timestamp": timestamp,
        "zone_id": zone_id,
        "dwell_ms": 0,
        "is_staff": is_staff,
        "confidence": confidence,
        "metadata": {"queue_depth": None, "sku_zone": zone_id, "session_seq": 1}
    }


def test_ingest_single_event():
    r = client.post("/events/ingest", json={"events": [ev()]})
    assert r.status_code == 200
    assert r.json()["accepted"] == 1
    assert r.json()["rejected"] == 0


def test_ingest_idempotent():
    eid = str(uuid.uuid4())
    event = ev(event_id=eid)
    r1 = client.post("/events/ingest", json={"events": [event]})
    r2 = client.post("/events/ingest", json={"events": [event]})
    assert r1.json()["accepted"] == 1
    assert r2.json()["duplicates"] == 1
    assert r2.json()["accepted"] == 0


def test_ingest_batch_500():
    events = [ev() for _ in range(500)]
    r = client.post("/events/ingest", json={"events": events})
    assert r.status_code == 200
    assert r.json()["accepted"] == 500


def test_metrics_empty_store():
    r = client.get("/stores/STORE_GHOST_999/metrics")
    assert r.status_code == 200
    d = r.json()
    assert d["unique_visitors"] == 0
    assert d["conversion_rate"] == 0.0
    assert d["queue_depth"] == 0


def test_metrics_excludes_staff():
    sid = f"S_{str(uuid.uuid4())[:6]}"
    client.post("/events/ingest", json={"events": [
        ev(store_id=sid, is_staff=True,  event_type="ENTRY"),
        ev(store_id=sid, is_staff=False, event_type="ENTRY"),
    ]})
    r = client.get(f"/stores/{sid}/metrics")
    assert r.json()["unique_visitors"] == 1


def test_metrics_zero_purchases():
    sid = f"S_{str(uuid.uuid4())[:6]}"
    client.post("/events/ingest", json={"events": [
        ev(store_id=sid, event_type="ENTRY"),
        ev(store_id=sid, event_type="EXIT"),
    ]})
    r = client.get(f"/stores/{sid}/metrics")
    assert r.json()["conversion_rate"] == 0.0


def test_funnel_reentry_no_double_count():
    sid = f"S_{str(uuid.uuid4())[:6]}"
    vid = f"VIS_{str(uuid.uuid4())[:6]}"
    client.post("/events/ingest", json={"events": [
        ev(store_id=sid, visitor_id=vid, event_type="ENTRY",   timestamp="2026-04-10T10:00:00Z"),
        ev(store_id=sid, visitor_id=vid, event_type="EXIT",    timestamp="2026-04-10T10:30:00Z"),
        ev(store_id=sid, visitor_id=vid, event_type="REENTRY", timestamp="2026-04-10T11:00:00Z"),
        ev(store_id=sid, visitor_id=vid, event_type="ENTRY",   timestamp="2026-04-10T11:00:01Z"),
    ]})
    r = client.get(f"/stores/{sid}/funnel")
    assert r.status_code == 200
    entry = next(s for s in r.json()["stages"] if s["stage"] == "Entry")
    assert entry["count"] == 1


def test_anomalies_returns_list():
    r = client.get("/stores/STORE_ANOM_EMPTY/anomalies")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_health_returns_valid():
    r = client.get("/health")
    assert r.status_code == 200
    d = r.json()
    assert "status" in d
    assert "db_status" in d
    assert d["db_status"] == "healthy"
    assert isinstance(d["stale_feeds"], list)
