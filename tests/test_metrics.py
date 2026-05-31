# PROMPT: "Generate pytest tests for /metrics, /funnel, /heatmap endpoints for retail
# store API. Cover: conversion rate formula, abandonment rate, staff exclusion, zero
# purchases, heatmap normalization, data_confidence flag, funnel drop-off range."
# CHANGES MADE: Updated store_id to ST1008 (Brigade Bangalore), added unique store IDs
# per test to prevent data contamination, fixed timestamp to ISO-8601Z format.

import pytest, uuid, sys
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append("../app")
from main import app
from database import Base, get_db

engine = create_engine("sqlite:///./test_metrics.db", connect_args={"check_same_thread": False})
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
       is_staff=False, confidence=0.91, timestamp="2026-04-10T10:00:00Z",
       dwell_ms=0, queue_depth=None):
    return {
        "event_id": str(uuid.uuid4()),
        "store_id": store_id,
        "camera_id": "CAM_2",
        "visitor_id": visitor_id or f"VIS_{str(uuid.uuid4())[:6]}",
        "event_type": event_type,
        "timestamp": timestamp,
        "zone_id": zone_id,
        "dwell_ms": dwell_ms,
        "is_staff": is_staff,
        "confidence": confidence,
        "metadata": {"queue_depth": queue_depth, "sku_zone": zone_id, "session_seq": 1}
    }


def test_metrics_unique_visitors():
    sid = f"S_{str(uuid.uuid4())[:6]}"
    client.post("/events/ingest", json={"events": [ev(sid, event_type="ENTRY") for _ in range(3)]})
    r = client.get(f"/stores/{sid}/metrics")
    assert r.status_code == 200
    assert r.json()["unique_visitors"] == 3


def test_metrics_abandonment_rate():
    sid = f"S_{str(uuid.uuid4())[:6]}"
    v1 = f"VIS_{str(uuid.uuid4())[:6]}"
    v2 = f"VIS_{str(uuid.uuid4())[:6]}"
    client.post("/events/ingest", json={"events": [
        ev(sid, visitor_id=v1, event_type="BILLING_QUEUE_JOIN", zone_id="BILLING", queue_depth=2),
        ev(sid, visitor_id=v2, event_type="BILLING_QUEUE_JOIN", zone_id="BILLING", queue_depth=2),
        ev(sid, visitor_id=v1, event_type="BILLING_QUEUE_ABANDON", zone_id="BILLING"),
    ]})
    r = client.get(f"/stores/{sid}/metrics")
    assert r.json()["abandonment_rate"] == 50.0


def test_metrics_zero_traffic():
    r = client.get("/stores/STORE_NOBODY_999/metrics")
    assert r.status_code == 200
    d = r.json()
    assert d["unique_visitors"] == 0
    assert d["conversion_rate"] == 0.0
    assert d["queue_depth"] == 0
    assert d["abandonment_rate"] == 0.0


def test_metrics_staff_excluded():
    sid = f"S_{str(uuid.uuid4())[:6]}"
    client.post("/events/ingest", json={"events": [
        ev(sid, event_type="ENTRY", is_staff=False),
        ev(sid, event_type="ENTRY", is_staff=True),
        ev(sid, event_type="ENTRY", is_staff=True),
    ]})
    r = client.get(f"/stores/{sid}/metrics")
    assert r.json()["unique_visitors"] == 1


def test_metrics_zero_purchases():
    sid = f"S_{str(uuid.uuid4())[:6]}"
    client.post("/events/ingest", json={"events": [
        ev(sid, event_type="ENTRY"),
        ev(sid, event_type="ZONE_ENTER", zone_id="SKIN"),
        ev(sid, event_type="EXIT"),
    ]})
    r = client.get(f"/stores/{sid}/metrics")
    assert r.json()["conversion_rate"] == 0.0


def test_heatmap_normalized_0_100():
    sid = f"S_{str(uuid.uuid4())[:6]}"
    for zone in ["SKIN", "MAKEUP", "BILLING", "FRAGRANCE"]:
        client.post("/events/ingest", json={"events": [
            ev(sid, event_type="ZONE_DWELL", zone_id=zone, dwell_ms=45000)
        ]})
    r = client.get(f"/stores/{sid}/heatmap")
    assert r.status_code == 200
    for z in r.json()["zones"]:
        assert 0.0 <= z["normalized_score"] <= 100.0


def test_heatmap_top_zone_100():
    sid = f"S_{str(uuid.uuid4())[:6]}"
    for _ in range(5):
        client.post("/events/ingest", json={"events": [
            ev(sid, event_type="ZONE_DWELL", zone_id="SKIN", dwell_ms=35000)
        ]})
    client.post("/events/ingest", json={"events": [
        ev(sid, event_type="ZONE_DWELL", zone_id="MAKEUP", dwell_ms=35000)
    ]})
    r = client.get(f"/stores/{sid}/heatmap")
    zones = {z["zone_id"]: z["normalized_score"] for z in r.json()["zones"]}
    assert zones.get("SKIN") == 100.0


def test_heatmap_data_confidence_low():
    sid = f"S_{str(uuid.uuid4())[:6]}"
    for _ in range(5):
        client.post("/events/ingest", json={"events": [
            ev(sid, event_type="ZONE_DWELL", zone_id="HAIR", dwell_ms=35000)
        ]})
    r = client.get(f"/stores/{sid}/heatmap")
    for z in r.json()["zones"]:
        if z["zone_id"] == "HAIR":
            assert z["data_confidence"] == False


def test_heatmap_empty_store():
    r = client.get("/stores/STORE_HEATMAP_EMPTY/heatmap")
    assert r.status_code == 200
    assert r.json()["zones"] == []


def test_funnel_drop_off_valid_range():
    sid = f"S_{str(uuid.uuid4())[:6]}"
    for _ in range(5):
        client.post("/events/ingest", json={"events": [
            ev(sid, event_type="ENTRY"),
            ev(sid, event_type="ZONE_ENTER", zone_id="SKIN"),
        ]})
    r = client.get(f"/stores/{sid}/funnel")
    for stage in r.json()["stages"]:
        assert 0.0 <= stage["drop_off_pct"] <= 100.0
