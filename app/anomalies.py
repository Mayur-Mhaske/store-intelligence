from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from database import EventDB
from models import Anomaly, AnomalySeverity
from datetime import datetime, timedelta
from typing import List
import structlog

logger = structlog.get_logger()


def detect_anomalies(store_id: str, db: Session) -> List[Anomaly]:
    anomalies = []
    now = datetime.utcnow()

    # 1. BILLING QUEUE SPIKE
    latest_q = db.query(EventDB).filter(
        EventDB.store_id == store_id,
        EventDB.event_type == "BILLING_QUEUE_JOIN",
        EventDB.timestamp >= now - timedelta(minutes=15)
    ).order_by(EventDB.timestamp.desc()).first()

    if latest_q and latest_q.metadata_json:
        qd = latest_q.metadata_json.get("queue_depth", 0) or 0
        if qd >= 8:
            anomalies.append(Anomaly(
                store_id=store_id, anomaly_type="BILLING_QUEUE_SPIKE",
                severity=AnomalySeverity.CRITICAL,
                description=f"Billing queue depth is {qd} — critically high",
                suggested_action="Open additional billing counters immediately. Call supervisor.",
                detected_at=now, metadata={"queue_depth": qd}
            ))
        elif qd >= 5:
            anomalies.append(Anomaly(
                store_id=store_id, anomaly_type="BILLING_QUEUE_SPIKE",
                severity=AnomalySeverity.WARN,
                description=f"Billing queue depth is {qd} — building up",
                suggested_action="Consider opening an additional billing counter.",
                detected_at=now, metadata={"queue_depth": qd}
            ))

    # 2. CONVERSION DROP vs 7-day avg
    def conversion(start, end):
        v = db.query(func.count(func.distinct(EventDB.visitor_id))).filter(
            EventDB.store_id == store_id, EventDB.timestamp >= start,
            EventDB.timestamp <= end, EventDB.event_type == "ENTRY",
            EventDB.is_staff == False).scalar() or 0
        if v == 0:
            return 0.0
        p = db.query(func.count(func.distinct(EventDB.visitor_id))).filter(
            EventDB.store_id == store_id, EventDB.timestamp >= start,
            EventDB.timestamp <= end, EventDB.event_type == "BILLING_QUEUE_JOIN",
            EventDB.is_staff == False).scalar() or 0
        return p / v * 100

    today_rate = conversion(now - timedelta(hours=24), now)
    week_rate  = conversion(now - timedelta(days=7), now - timedelta(hours=24))

    if week_rate > 0:
        drop = (week_rate - today_rate) / week_rate * 100
        if drop >= 30:
            anomalies.append(Anomaly(
                store_id=store_id, anomaly_type="CONVERSION_DROP",
                severity=AnomalySeverity.CRITICAL,
                description=f"Conversion dropped {drop:.1f}% vs 7-day avg ({today_rate:.1f}% vs {week_rate:.1f}%)",
                suggested_action="Check staff, product placement, billing queue. Escalate to manager.",
                detected_at=now, metadata={"today": today_rate, "week_avg": week_rate}
            ))
        elif drop >= 15:
            anomalies.append(Anomaly(
                store_id=store_id, anomaly_type="CONVERSION_DROP",
                severity=AnomalySeverity.WARN,
                description=f"Conversion dropped {drop:.1f}% vs 7-day avg",
                suggested_action="Monitor closely. Check high abandonment zones.",
                detected_at=now, metadata={"today": today_rate, "week_avg": week_rate}
            ))

    # 3. DEAD ZONE
    recent_zones = {r[0] for r in db.query(func.distinct(EventDB.zone_id)).filter(
        EventDB.store_id == store_id,
        EventDB.timestamp >= now - timedelta(minutes=30),
        EventDB.zone_id.isnot(None), EventDB.is_staff == False
    ).all()}
    all_zones = {r[0] for r in db.query(func.distinct(EventDB.zone_id)).filter(
        EventDB.store_id == store_id, EventDB.zone_id.isnot(None)
    ).all()}

    for zone in (all_zones - recent_zones):
        anomalies.append(Anomaly(
            store_id=store_id, anomaly_type="DEAD_ZONE",
            severity=AnomalySeverity.INFO,
            description=f"Zone '{zone}' has had no visits in the last 30 minutes",
            suggested_action="Check if zone is blocked, poorly lit, or needs staff attention.",
            detected_at=now, metadata={"zone_id": zone}
        ))

    # 4. STALE FEED
    latest = db.query(EventDB).filter(
        EventDB.store_id == store_id
    ).order_by(EventDB.timestamp.desc()).first()

    if latest:
        lag = (now - latest.timestamp).total_seconds() / 60
        if lag > 10:
            anomalies.append(Anomaly(
                store_id=store_id, anomaly_type="STALE_FEED",
                severity=AnomalySeverity.CRITICAL,
                description=f"No events in {lag:.1f} minutes",
                suggested_action="Check camera connectivity and detection pipeline.",
                detected_at=now, metadata={"lag_minutes": lag}
            ))

    logger.info("anomalies_detected", store_id=store_id, count=len(anomalies))
    return anomalies
