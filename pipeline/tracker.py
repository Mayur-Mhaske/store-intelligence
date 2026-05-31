import uuid, math
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

DWELL_INTERVAL_MS = 30_000
REENTRY_MAX_SECONDS = 300
REENTRY_SPATIAL_PX = 150


class VisitorSession:
    def __init__(self, track_id, visitor_id, first_seen):
        self.track_id = track_id
        self.visitor_id = visitor_id
        self.first_seen = first_seen
        self.last_seen = first_seen
        self.current_zone = None
        self.zone_enter_time = None
        self.last_dwell_emit = None
        self.session_seq = 0
        self.crossed_entry = False
        self.is_staff = False
        self.last_cx = 0.0
        self.last_cy = 0.0


class VisitorTracker:
    def __init__(self):
        self.active: Dict[int, VisitorSession] = {}
        self.exited: Dict[str, Tuple] = {}
        self.track_to_visitor: Dict[int, str] = {}
        self.prev_cy: Dict[int, float] = {}

    def _new_vid(self):
        return "VIS_" + str(uuid.uuid4())[:6]

    def get_visitor_id(self, track_id):
        return self.track_to_visitor.get(track_id, f"VIS_UNK_{track_id}")

    def _check_reentry(self, cx, cy, ts):
        for vid, (exit_time, ex, ey) in list(self.exited.items()):
            secs = (ts - exit_time).total_seconds()
            dist = math.sqrt((cx - ex) ** 2 + (cy - ey) ** 2)
            if secs < REENTRY_MAX_SECONDS and dist < REENTRY_SPATIAL_PX:
                return vid
        return None

    def _seq(self, session):
        session.session_seq += 1
        return session.session_seq

    def update(self, track_id, cx, cy, zone_id, is_staff, confidence, timestamp, entry_line_y, frame_height):
        events = []

        if track_id not in self.active:
            reentry_vid = self._check_reentry(cx, cy, timestamp)
            if reentry_vid:
                visitor_id = reentry_vid
                del self.exited[reentry_vid]
                events.append(("REENTRY", {}))
            else:
                visitor_id = self._new_vid()
            self.track_to_visitor[track_id] = visitor_id
            session = VisitorSession(track_id, visitor_id, timestamp)
            session.last_cx = cx
            session.last_cy = cy
            session.is_staff = bool(is_staff)
            self.active[track_id] = session

        session = self.active[track_id]
        session.last_seen = timestamp
        prev = self.prev_cy.get(track_id, cy)

        if not session.crossed_entry and prev < entry_line_y <= cy:
            session.crossed_entry = True
            events.append(("ENTRY", {"session_seq": self._seq(session)}))

        if zone_id != session.current_zone:
            if session.current_zone is not None:
                dwell = int((timestamp - session.zone_enter_time).total_seconds() * 1000) if session.zone_enter_time else 0
                events.append(("ZONE_EXIT", {"dwell_ms": dwell, "session_seq": self._seq(session)}))
            session.current_zone = zone_id
            session.zone_enter_time = timestamp
            session.last_dwell_emit = timestamp
            events.append(("ZONE_ENTER", {"session_seq": self._seq(session)}))

        if session.zone_enter_time and session.last_dwell_emit:
            in_zone_ms = (timestamp - session.zone_enter_time).total_seconds() * 1000
            since_dwell = (timestamp - session.last_dwell_emit).total_seconds() * 1000
            if in_zone_ms >= DWELL_INTERVAL_MS and since_dwell >= DWELL_INTERVAL_MS:
                events.append(("ZONE_DWELL", {"dwell_ms": int(in_zone_ms), "session_seq": self._seq(session)}))
                session.last_dwell_emit = timestamp

        if zone_id == "BILLING":
            billing_count = sum(1 for s in self.active.values()
                                if s.current_zone == "BILLING" and not s.is_staff)
            if billing_count > 1:
                events.append(("BILLING_QUEUE_JOIN", {"queue_depth": billing_count, "session_seq": self._seq(session)}))

        session.last_cx = cx
        session.last_cy = cy
        session.is_staff = bool(is_staff)
        self.prev_cy[track_id] = cy
        return events

    def flush_exits(self, timestamp):
        exit_events = []
        for track_id, session in list(self.active.items()):
            vid = session.visitor_id
            if session.current_zone == "BILLING":
                exit_events.append({
                    "event_id": str(uuid.uuid4()), "store_id": "ST1008",
                    "camera_id": "CAM_FLUSH", "visitor_id": vid,
                    "event_type": "BILLING_QUEUE_ABANDON",
                    "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "zone_id": "BILLING", "dwell_ms": 0, "is_staff": bool(session.is_staff),
                    "confidence": 0.9,
                    "metadata": {"queue_depth": None, "sku_zone": "BILLING", "session_seq": session.session_seq + 1}
                })
            exit_events.append({
                "event_id": str(uuid.uuid4()), "store_id": "ST1008",
                "camera_id": "CAM_FLUSH", "visitor_id": vid,
                "event_type": "EXIT",
                "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "zone_id": None, "dwell_ms": 0, "is_staff": bool(session.is_staff),
                "confidence": 0.9,
                "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": session.session_seq + 2}
            })
            self.exited[vid] = (timestamp, session.last_cx, session.last_cy)
        self.active.clear()
        return exit_events
