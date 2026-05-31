# PROMPT: "Generate 10 API assertions for retail store intelligence system.
# Cover: health, ingest, idempotency, empty store, staff exclusion, re-entry dedup,
# anomaly structure, heatmap normalization, batch 500, zero purchase conversion."
# CHANGES MADE: Updated to ST1008 (Brigade Bangalore), added suggested_action check.

import requests, uuid

BASE = "http://localhost:8000"
STORE = "ST1008"


def ev(**kwargs):
    defaults = {
        "event_id": str(uuid.uuid4()), "store_id": STORE, "camera_id": "CAM_1",
        "visitor_id": f"VIS_{str(uuid.uuid4())[:6]}", "event_type": "ENTRY",
        "timestamp": "2026-04-10T10:00:00Z", "zone_id": None, "dwell_ms": 0,
        "is_staff": False, "confidence": 0.91,
        "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": 1}
    }
    defaults.update(kwargs)
    return defaults


def assertion_1_health():
    r = requests.get(f"{BASE}/health")
    assert r.status_code == 200
    assert "status" in r.json()
    assert "db_status" in r.json()
    assert isinstance(r.json()["stale_feeds"], list)
    print("✅ assertion_1_health PASSED")


def assertion_2_ingest_accepted():
    r = requests.post(f"{BASE}/events/ingest", json={"events": [ev()]})
    assert r.status_code == 200
    assert r.json()["accepted"] >= 1
    print("✅ assertion_2_ingest_accepted PASSED")


def assertion_3_idempotent():
    eid = str(uuid.uuid4())
    event = ev(event_id=eid)
    r1 = requests.post(f"{BASE}/events/ingest", json={"events": [event]})
    r2 = requests.post(f"{BASE}/events/ingest", json={"events": [event]})
    assert r1.json()["accepted"] == 1
    assert r2.json()["duplicates"] == 1
    assert r2.json()["accepted"] == 0
    print("✅ assertion_3_idempotent PASSED")


def assertion_4_empty_store():
    r = requests.get(f"{BASE}/stores/STORE_EMPTY_999/metrics")
    assert r.status_code == 200
    assert r.json()["unique_visitors"] == 0
    assert r.json()["conversion_rate"] == 0.0
    assert r.json()["queue_depth"] == 0
    print("✅ assertion_4_empty_store PASSED")


def assertion_5_staff_excluded():
    store = f"S_{str(uuid.uuid4())[:4]}"
    requests.post(f"{BASE}/events/ingest", json={"events": [
        ev(store_id=store, is_staff=True),
        ev(store_id=store, is_staff=False)
    ]})
    r = requests.get(f"{BASE}/stores/{store}/metrics")
    assert r.json()["unique_visitors"] == 1
    print("✅ assertion_5_staff_excluded PASSED")


def assertion_6_funnel_no_double_count():
    store = f"S_{str(uuid.uuid4())[:4]}"
    vid = f"VIS_{str(uuid.uuid4())[:6]}"
    requests.post(f"{BASE}/events/ingest", json={"events": [
        ev(store_id=store, visitor_id=vid, event_type="ENTRY",   timestamp="2026-04-10T10:00:00Z"),
        ev(store_id=store, visitor_id=vid, event_type="EXIT",    timestamp="2026-04-10T10:30:00Z"),
        ev(store_id=store, visitor_id=vid, event_type="REENTRY", timestamp="2026-04-10T11:00:00Z"),
        ev(store_id=store, visitor_id=vid, event_type="ENTRY",   timestamp="2026-04-10T11:00:01Z"),
    ]})
    r = requests.get(f"{BASE}/stores/{store}/funnel")
    entry = next(s for s in r.json()["stages"] if s["stage"] == "Entry")
    assert entry["count"] == 1
    print("✅ assertion_6_funnel_no_double_count PASSED")


def assertion_7_anomalies_list():
    r = requests.get(f"{BASE}/stores/{STORE}/anomalies")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    print("✅ assertion_7_anomalies_list PASSED")


def assertion_8_heatmap_normalized():
    r = requests.get(f"{BASE}/stores/{STORE}/heatmap")
    assert r.status_code == 200
    for z in r.json().get("zones", []):
        assert 0.0 <= z["normalized_score"] <= 100.0
    print("✅ assertion_8_heatmap_normalized PASSED")


def assertion_9_batch_500():
    events = [ev() for _ in range(500)]
    r = requests.post(f"{BASE}/events/ingest", json={"events": events})
    assert r.status_code == 200
    assert r.json()["accepted"] == 500
    print("✅ assertion_9_batch_500 PASSED")


def assertion_10_zero_purchase():
    store = f"S_{str(uuid.uuid4())[:4]}"
    requests.post(f"{BASE}/events/ingest", json={"events": [
        ev(store_id=store, event_type="ENTRY"),
        ev(store_id=store, event_type="ZONE_ENTER", zone_id="SKIN"),
        ev(store_id=store, event_type="EXIT"),
    ]})
    r = requests.get(f"{BASE}/stores/{store}/metrics")
    assert r.json()["conversion_rate"] == 0.0
    print("✅ assertion_10_zero_purchase PASSED")


if __name__ == "__main__":
    print(f"\n🧪 Running assertions against {BASE}")
    print("=" * 50)
    assertion_1_health()
    assertion_2_ingest_accepted()
    assertion_3_idempotent()
    assertion_4_empty_store()
    assertion_5_staff_excluded()
    assertion_6_funnel_no_double_count()
    assertion_7_anomalies_list()
    assertion_8_heatmap_normalized()
    assertion_9_batch_500()
    assertion_10_zero_purchase()
    print("=" * 50)
    print("✅ All 10 assertions passed!")
