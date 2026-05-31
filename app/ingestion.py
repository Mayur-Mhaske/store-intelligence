from sqlalchemy.orm import Session
from models import StoreEvent, EventBatch, IngestResponse
from database import EventDB
import structlog

logger = structlog.get_logger()


def ingest_events(batch: EventBatch, db: Session) -> IngestResponse:
    accepted = 0
    rejected = 0
    duplicates = 0
    errors = []

    for event in batch.events:
        try:
            existing = db.query(EventDB).filter(EventDB.event_id == event.event_id).first()
            if existing:
                duplicates += 1
                continue

            db_event = EventDB(
                event_id      = event.event_id,
                store_id      = event.store_id,
                camera_id     = event.camera_id,
                visitor_id    = event.visitor_id,
                event_type    = event.event_type.value,
                timestamp     = event.timestamp,
                zone_id       = event.zone_id,
                dwell_ms      = event.dwell_ms,
                is_staff      = event.is_staff,
                confidence    = event.confidence,
                metadata_json = event.metadata.model_dump()
            )
            db.add(db_event)
            accepted += 1

        except Exception as e:
            rejected += 1
            errors.append({"event_id": event.event_id, "error": str(e)})
            logger.error("ingest_error", event_id=event.event_id, error=str(e))

    db.commit()
    logger.info("batch_ingested", accepted=accepted, rejected=rejected, duplicates=duplicates)
    return IngestResponse(accepted=accepted, rejected=rejected, duplicates=duplicates, errors=errors)
