"""
generate_mock_events.py — Synthetic events for Brigade Bangalore (ST1008)
Usage: python generate_mock_events.py --visitors 60 --output ../events_output/mock.jsonl
"""
import uuid, json, random, argparse, os
from datetime import datetime, timedelta

STORE_ID = "ST1008"
ZONES = ["SKIN", "HAIR", "FRAGRANCE", "MAKEUP", "PERSONAL_CARE", "BATH_BODY", "OFFERS"]


def ev(visitor_id, event_type, timestamp, camera_id="CAM_2", zone_id=None,
       dwell_ms=0, is_staff=False, confidence=0.91, queue_depth=None, seq=1):
    return {
        "event_id": str(uuid.uuid4()),
        "store_id": STORE_ID,
        "camera_id": camera_id,
        "visitor_id": visitor_id,
        "event_type": event_type,
        "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "zone_id": zone_id,
        "dwell_ms": dwell_ms,
        "is_staff": is_staff,
        "confidence": round(confidence, 4),
        "metadata": {"queue_depth": queue_depth, "sku_zone": zone_id, "session_seq": seq}
    }


def simulate_visitor(start_time, visitor_id=None, is_reentry=False):
    events = []
    t = start_time
    vid = visitor_id or f"VIS_{str(uuid.uuid4())[:6]}"
    seq = 0

    def s():
        nonlocal seq
        seq += 1
        return seq

    if is_reentry:
        events.append(ev(vid, "REENTRY", t, camera_id="CAM_1", seq=s()))
    events.append(ev(vid, "ENTRY", t, camera_id="CAM_1", seq=s()))
    t += timedelta(seconds=random.randint(5, 15))

    for zone in random.sample(ZONES, random.randint(2, 4)):
        events.append(ev(vid, "ZONE_ENTER", t, zone_id=zone, seq=s()))
        dwell = random.randint(15, 200) * 1000
        t += timedelta(milliseconds=dwell)
        if dwell >= 30000:
            events.append(ev(vid, "ZONE_DWELL", t, zone_id=zone, dwell_ms=dwell, seq=s()))
        events.append(ev(vid, "ZONE_EXIT", t, zone_id=zone, dwell_ms=dwell, seq=s()))
        t += timedelta(seconds=random.randint(5, 20))

    if random.random() < 0.6:
        qd = random.randint(0, 7)
        events.append(ev(vid, "ZONE_ENTER", t, camera_id="CAM_3", zone_id="BILLING", seq=s()))
        if qd > 0:
            events.append(ev(vid, "BILLING_QUEUE_JOIN", t, camera_id="CAM_3", zone_id="BILLING", queue_depth=qd, seq=s()))
        if qd > 3 and random.random() < 0.25:
            t += timedelta(seconds=random.randint(30, 90))
            events.append(ev(vid, "BILLING_QUEUE_ABANDON", t, camera_id="CAM_3", zone_id="BILLING", seq=s()))
        else:
            t += timedelta(seconds=random.randint(60, 300))

    events.append(ev(vid, "EXIT", t, camera_id="CAM_1", seq=s()))
    return events, vid, t


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="../events_output/mock.jsonl")
    parser.add_argument("--visitors", type=int, default=60)
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)

    all_events = []
    t = datetime.utcnow().replace(hour=10, minute=0, second=0, microsecond=0)
    past_visitors = []

    # 3 staff members
    for _ in range(3):
        for zone in ZONES:
            sid = f"STAFF_{str(uuid.uuid4())[:4]}"
            all_events.append(ev(sid, "ZONE_ENTER", t + timedelta(minutes=random.randint(0, 30)),
                                  zone_id=zone, is_staff=True, confidence=0.97))

    for i in range(args.visitors):
        t += timedelta(seconds=random.randint(30, 120))
        group = random.choices([1, 2, 3], weights=[80, 15, 5])[0]
        for _ in range(group):
            events, vid, exit_t = simulate_visitor(t)
            all_events.extend(events)
            past_visitors.append((vid, exit_t))

    for vid, exit_t in random.sample(past_visitors, max(1, len(past_visitors) // 7)):
        reentry_t = exit_t + timedelta(minutes=random.randint(5, 25))
        events, _, _ = simulate_visitor(reentry_t, visitor_id=vid, is_reentry=True)
        all_events.extend(events)

    all_events.sort(key=lambda e: e["timestamp"])

    with open(args.output, "w") as f:
        for e in all_events:
            f.write(json.dumps(e) + "\n")

    print(f"✅ {len(all_events)} mock events → {args.output}")


if __name__ == "__main__":
    main()
