import uuid, json
from datetime import datetime
from typing import Optional
import requests


class EventEmitter:
    def __init__(self, store_id, camera_id):
        self.store_id = store_id
        self.camera_id = camera_id

    def emit(self, event_type, visitor_id, timestamp, zone_id, is_staff, confidence, extra={}):
        return {
            "event_id": str(uuid.uuid4()),
            "store_id": self.store_id,
            "camera_id": self.camera_id,
            "visitor_id": visitor_id,
            "event_type": event_type,
            "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "zone_id": zone_id,
            "dwell_ms": int(extra.get("dwell_ms", 0)),
            "is_staff": bool(is_staff),
            "confidence": float(round(confidence, 4)),
            "metadata": {
                "queue_depth": extra.get("queue_depth", None),
                "sku_zone": zone_id,
                "session_seq": int(extra.get("session_seq", 1))
            }
        }


def replay_to_api(jsonl_path, api_url="http://localhost:8000", batch_size=100):
    events = []
    with open(jsonl_path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    print(f"Replaying {len(events)} events to {api_url}...")
    total_accepted = 0

    for i in range(0, len(events), batch_size):
        batch = events[i:i + batch_size]
        try:
            resp = requests.post(f"{api_url}/events/ingest", json={"events": batch}, timeout=10)
            if resp.status_code == 200:
                r = resp.json()
                total_accepted += r.get("accepted", 0)
                print(f"  Batch {i//batch_size + 1}: accepted={r['accepted']} dupes={r['duplicates']}")
            else:
                print(f"  Batch {i//batch_size + 1} ERROR: {resp.status_code}")
        except Exception as e:
            print(f"  Batch {i//batch_size + 1} FAILED: {e}")

    print(f"\n✅ Done! {total_accepted}/{len(events)} events accepted.")
