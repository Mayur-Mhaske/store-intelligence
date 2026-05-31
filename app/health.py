from sqlalchemy.orm import Session
from sqlalchemy import func
from database import EventDB, check_db_health
from models import HealthStatus
from datetime import datetime, timedelta
import time

START_TIME = time.time()


def get_health(db: Session) -> HealthStatus:
    now = datetime.utcnow()
    rows = db.query(
        EventDB.store_id,
        func.max(EventDB.timestamp).label("last_event")
    ).group_by(EventDB.store_id).all()

    last_event_per_store = {}
    stale_feeds = []

    for r in rows:
        last_event_per_store[r.store_id] = r.last_event.isoformat()
        if (now - r.last_event).total_seconds() / 60 > 10:
            stale_feeds.append(r.store_id)

    db_status = check_db_health()
    overall = "degraded" if db_status != "healthy" or stale_feeds else "healthy"

    return HealthStatus(
        status=overall,
        last_event_per_store=last_event_per_store,
        stale_feeds=stale_feeds,
        uptime_seconds=round(time.time() - START_TIME, 2),
        db_status=db_status
    )
