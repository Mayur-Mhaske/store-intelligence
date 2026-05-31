from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from database import EventDB
from models import StoreFunnel, FunnelStage
from datetime import datetime, timedelta


def get_store_funnel(store_id: str, db: Session, hours: int = 24) -> StoreFunnel:
    end = datetime.utcnow()
    start = end - timedelta(hours=hours)

    def distinct_visitors(etype):
        return db.query(func.count(func.distinct(EventDB.visitor_id))).filter(
            EventDB.store_id == store_id, EventDB.timestamp >= start,
            EventDB.event_type == etype, EventDB.is_staff == False
        ).scalar() or 0

    entry   = distinct_visitors("ENTRY")
    zone    = distinct_visitors("ZONE_ENTER")
    billing = distinct_visitors("BILLING_QUEUE_JOIN")

    billed_ids  = {r[0] for r in db.query(func.distinct(EventDB.visitor_id)).filter(
        EventDB.store_id == store_id, EventDB.timestamp >= start,
        EventDB.event_type == "BILLING_QUEUE_JOIN", EventDB.is_staff == False).all()}
    abandon_ids = {r[0] for r in db.query(func.distinct(EventDB.visitor_id)).filter(
        EventDB.store_id == store_id, EventDB.timestamp >= start,
        EventDB.event_type == "BILLING_QUEUE_ABANDON", EventDB.is_staff == False).all()}
    purchased = len(billed_ids - abandon_ids)

    def drop(cur, prev):
        return round((1 - cur / prev) * 100, 2) if prev > 0 else 0.0

    stages = [
        FunnelStage(stage="Entry",         count=entry,     drop_off_pct=0.0),
        FunnelStage(stage="Zone Visit",    count=zone,      drop_off_pct=drop(zone, entry)),
        FunnelStage(stage="Billing Queue", count=billing,   drop_off_pct=drop(billing, zone)),
        FunnelStage(stage="Purchase",      count=purchased, drop_off_pct=drop(purchased, billing)),
    ]
    return StoreFunnel(store_id=store_id, stages=stages, window_start=start, window_end=end)
