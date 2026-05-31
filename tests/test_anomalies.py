# PROMPT: "Generate pytest tests for anomaly detection in retail store API. Cover:
# BILLING_QUEUE_SPIKE at WARN (5+) and CRITICAL (8+) thresholds, DEAD_ZONE after
# 30min inactivity, STALE_FEED after 10min lag, anomaly required fields validation,
# no anomaly on low queue depth."
# CHANGES MADE: Added datetime-based timestamps for stale feed test, verified
# suggested_action is non-empty, added severity enum validation.

import pytest, uuid, sys
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta

sys.path.append("../app")
from main import app
from database import Base, get_db

engine = create_engine("sqlite:///./test_anomalies.db", connect_args={"check_same_thread": False})
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


def ev(store_id, visitor_id=None, event_type="ENTRY", zone_id=None,
       is_staff=False, timestamp=None, queue_depth=None, confidence=0.91):
    ts = timestamp or datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "event_id": str(uuid.uuid4()),
        "store_id": store_id,
        "camera_id": "CAM_3",
        "visitor_id": visitor_id or f"VIS_{str(uuid.uuid4())[:6]}",
        "event_type": event_type,
        "timestamp": ts,
        "zone_id": zone_id,
        "dwell_ms": 0,
        "is_staff": is_staff,
        "confidence": confidence,
        "metadata": {"queue_depth": queue_depth, "sku_zone": zone_id, "session_seq": 1}
    }


def test_anomalies_empty_store():
    r = client.get("/stores/STORE_ANOM_NONE/anomalies")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_anomaly_has_required_fields():
    sid = f"S_{str(uuid.uuid4())[:6]}"
    client.post("/events/ingest", json={"events": [
        ev(sid, event_type="BILLING_QUEUE_JOIN", zone_id="BILLING", queue_depth=9)
    ]})
    r = client.get(f"/stores/{sid}/anomalies")
    if r.json():
        a = r.json()[0]
        assert "anomaly_type" in a
        assert "severity" in a
        assert "description" in a
        assert "suggested_action" in a
        assert a["suggested_action"] != ""
        assert a["severity"] in ["INFO", "WARN", "CRITICAL"]


def test_billing_queue_spike_critical():
    sid = f"S_{str(uuid.uuid4())[:6]}"
    client.post("/events/ingest", json={"events": [
        ev(sid, event_type="BILLING_QUEUE_JOIN", zone_id="BILLING", queue_depth=9)
    ]})
    r = client.get(f"/stores/{sid}/anomalies")
    spike = [a for a in r.json() if a["anomaly_type"] == "BILLING_QUEUE_SPIKE"]
    assert len(spike) > 0
    assert spike[0]["severity"] == "CRITICAL"


def test_billing_queue_spike_warn():
    sid = f"S_{str(uuid.uuid4())[:6]}"
    client.post("/events/ingest", json={"events": [
        ev(sid, event_type="BILLING_QUEUE_JOIN", zone_id="BILLING", queue_depth=6)
    ]})
    r = client.get(f"/stores/{sid}/anomalies")
    spike = [a for a in r.json() if a["anomaly_type"] == "BILLING_QUEUE_SPIKE"]
    assert len(spike) > 0
    assert spike[0]["severity"] == "WARN"


def test_no_spike_low_queue():
    sid = f"S_{str(uuid.uuid4())[:6]}"
    client.post("/events/ingest", json={"events": [
        ev(sid, event_type="BILLING_QUEUE_JOIN", zone_id="BILLING", queue_depth=2)
    ]})
    r = client.get(f"/stores/{sid}/anomalies")
    spike = [a for a in r.json() if a["anomaly_type"] == "BILLING_QUEUE_SPIKE"]
    assert len(spike) == 0


def test_dead_zone_detected():
    sid = f"S_{str(uuid.uuid4())[:6]}"
    old_ts = (datetime.utcnow() - timedelta(minutes=40)).strftime("%Y-%m-%dT%H:%M:%SZ")
    client.post("/events/ingest", json={"events": [
        ev(sid, event_type="ZONE_ENTER", zone_id="FRAGRANCE", timestamp=old_ts)
    ]})
    r = client.get(f"/stores/{sid}/anomalies")
    dead = [a for a in r.json() if a["anomaly_type"] == "DEAD_ZONE"]
    assert len(dead) > 0
    assert dead[0]["severity"] == "INFO"


def test_stale_feed_detected():
    sid = f"S_{str(uuid.uuid4())[:6]}"
    old_ts = (datetime.utcnow() - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
    client.post("/events/ingest", json={"events": [
        ev(sid, event_type="ENTRY", timestamp=old_ts)
    ]})
    r = client.get(f"/stores/{sid}/anomalies")
    stale = [a for a in r.json() if a["anomaly_type"] == "STALE_FEED"]
    assert len(stale) > 0
    assert stale[0]["severity"] == "CRITICAL"


def test_no_stale_feed_recent():
    sid = f"S_{str(uuid.uuid4())[:6]}"
    client.post("/events/ingest", json={"events": [ev(sid, event_type="ENTRY")]})
    r = client.get(f"/stores/{sid}/anomalies")
    stale = [a for a in r.json() if a["anomaly_type"] == "STALE_FEED"]
    assert len(stale) == 0


def test_health_db_healthy():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["db_status"] == "healthy"
    assert isinstance(r.json()["stale_feeds"], list)
