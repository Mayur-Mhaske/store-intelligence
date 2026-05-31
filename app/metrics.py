from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from database import EventDB
from models import StoreMetrics, ZoneMetric, StoreHeatmap, HeatmapZone
from datetime import datetime, timedelta
import csv, os
import structlog

logger = structlog.get_logger()

POS_FILE = os.path.join(os.path.dirname(__file__), "pos_transactions.csv")


def load_pos_transactions(store_id: str, start: datetime, end: datetime) -> list:
    """Load POS transactions for a store within a time window."""
    transactions = []
    try:
        with open(POS_FILE, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["store_id"] == store_id:
                    try:
                        ts = datetime.fromisoformat(row["timestamp"].replace("Z", ""))
                        if start <= ts <= end:
                            transactions.append({"timestamp": ts, "amount": float(row["basket_value_inr"])})
                    except Exception:
                        pass
    except FileNotFoundError:
        pass
    return transactions


def get_converted_visitors(store_id: str, db: Session, start: datetime, end: datetime) -> int:
    """
    POS correlation: visitor in billing zone within 5 min before transaction = converted.
    """
    transactions = load_pos_transactions(store_id, start, end)
    converted_visitors = set()

    for txn in transactions:
        window_start = txn["timestamp"] - timedelta(minutes=5)
        window_end = txn["timestamp"]

        billing_visitors = db.query(func.distinct(EventDB.visitor_id)).filter(
            EventDB.store_id == store_id,
            EventDB.zone_id == "BILLING",
            EventDB.timestamp >= window_start,
            EventDB.timestamp <= window_end,
            EventDB.is_staff == False
        ).all()

        for (vid,) in billing_visitors:
            converted_visitors.add(vid)

    return len(converted_visitors)


def _window(hours=24):
    end = datetime.utcnow()
    return end - timedelta(hours=hours), end


def get_store_metrics(store_id: str, db: Session, hours: int = 24) -> StoreMetrics:
    start, end = _window(hours)

    unique_visitors = db.query(func.count(func.distinct(EventDB.visitor_id))).filter(
        EventDB.store_id == store_id,
        EventDB.timestamp >= start,
        EventDB.event_type == "ENTRY",
        EventDB.is_staff == False
    ).scalar() or 0

    # POS-correlated conversion
    converted = get_converted_visitors(store_id, db, start, end)
    conversion_rate = round(converted / unique_visitors * 100, 2) if unique_visitors > 0 else 0.0

    billed = {r[0] for r in db.query(func.distinct(EventDB.visitor_id)).filter(
        EventDB.store_id == store_id, EventDB.timestamp >= start,
        EventDB.event_type == "BILLING_QUEUE_JOIN", EventDB.is_staff == False
    ).all()}
    abandoned = {r[0] for r in db.query(func.distinct(EventDB.visitor_id)).filter(
        EventDB.store_id == store_id, EventDB.timestamp >= start,
        EventDB.event_type == "BILLING_QUEUE_ABANDON", EventDB.is_staff == False
    ).all()}
    abandonment_rate = round(len(abandoned) / len(billed) * 100, 2) if billed else 0.0

    zone_rows = db.query(
        EventDB.zone_id,
        func.avg(EventDB.dwell_ms).label("avg_dwell"),
        func.count(EventDB.event_id).label("cnt")
    ).filter(
        EventDB.store_id == store_id, EventDB.timestamp >= start,
        EventDB.event_type == "ZONE_DWELL",
        EventDB.zone_id.isnot(None), EventDB.is_staff == False
    ).group_by(EventDB.zone_id).all()

    zone_metrics = [ZoneMetric(zone_id=r.zone_id, avg_dwell_ms=float(r.avg_dwell or 0),
                                visit_count=r.cnt, heatmap_score=0.0) for r in zone_rows]

    latest_q = db.query(EventDB).filter(
        EventDB.store_id == store_id, EventDB.event_type == "BILLING_QUEUE_JOIN"
    ).order_by(EventDB.timestamp.desc()).first()
    queue_depth = 0
    if latest_q and latest_q.metadata_json:
        queue_depth = latest_q.metadata_json.get("queue_depth") or 0

    return StoreMetrics(
        store_id=store_id,
        unique_visitors=unique_visitors,
        conversion_rate=conversion_rate,
        avg_dwell_per_zone=zone_metrics,
        queue_depth=queue_depth,
        abandonment_rate=abandonment_rate,
        window_start=start,
        window_end=end
    )


def get_store_heatmap(store_id: str, db: Session, hours: int = 24) -> StoreHeatmap:
    start, _ = _window(hours)
    rows = db.query(
        EventDB.zone_id,
        func.count(EventDB.event_id).label("visits"),
        func.avg(EventDB.dwell_ms).label("avg_dwell"),
        func.count(func.distinct(EventDB.visitor_id)).label("sessions")
    ).filter(
        EventDB.store_id == store_id, EventDB.timestamp >= start,
        EventDB.zone_id.isnot(None), EventDB.is_staff == False
    ).group_by(EventDB.zone_id).all()

    if not rows:
        return StoreHeatmap(store_id=store_id, zones=[], generated_at=datetime.utcnow())

    max_v = max(r.visits for r in rows) or 1
    zones = [HeatmapZone(
        zone_id=r.zone_id,
        visit_frequency=r.visits,
        avg_dwell_ms=float(r.avg_dwell or 0),
        normalized_score=round(r.visits / max_v * 100, 2),
        data_confidence=r.sessions >= 20
    ) for r in rows]

    return StoreHeatmap(store_id=store_id, zones=zones, generated_at=datetime.utcnow())
