from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum
import uuid


class EventType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    ZONE_ENTER = "ZONE_ENTER"
    ZONE_EXIT = "ZONE_EXIT"
    ZONE_DWELL = "ZONE_DWELL"
    BILLING_QUEUE_JOIN = "BILLING_QUEUE_JOIN"
    BILLING_QUEUE_ABANDON = "BILLING_QUEUE_ABANDON"
    REENTRY = "REENTRY"


class EventMetadata(BaseModel):
    queue_depth: Optional[int] = None
    sku_zone: Optional[str] = None
    session_seq: Optional[int] = None


class StoreEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    store_id: str
    camera_id: str
    visitor_id: str
    event_type: EventType
    timestamp: datetime
    zone_id: Optional[str] = None
    dwell_ms: int = 0
    is_staff: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: EventMetadata = Field(default_factory=EventMetadata)


class EventBatch(BaseModel):
    events: List[StoreEvent] = Field(max_length=500)


class IngestResponse(BaseModel):
    accepted: int
    rejected: int
    duplicates: int
    errors: List[dict] = []


class AnomalySeverity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"


class Anomaly(BaseModel):
    anomaly_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    store_id: str
    anomaly_type: str
    severity: AnomalySeverity
    description: str
    suggested_action: str
    detected_at: datetime
    metadata: dict = {}


class ZoneMetric(BaseModel):
    zone_id: str
    avg_dwell_ms: float
    visit_count: int
    heatmap_score: float = 0.0


class StoreMetrics(BaseModel):
    store_id: str
    unique_visitors: int
    conversion_rate: float
    avg_dwell_per_zone: List[ZoneMetric]
    queue_depth: int
    abandonment_rate: float
    window_start: datetime
    window_end: datetime


class FunnelStage(BaseModel):
    stage: str
    count: int
    drop_off_pct: float


class StoreFunnel(BaseModel):
    store_id: str
    stages: List[FunnelStage]
    window_start: datetime
    window_end: datetime


class HeatmapZone(BaseModel):
    zone_id: str
    visit_frequency: int
    avg_dwell_ms: float
    normalized_score: float
    data_confidence: bool


class StoreHeatmap(BaseModel):
    store_id: str
    zones: List[HeatmapZone]
    generated_at: datetime


class HealthStatus(BaseModel):
    status: str
    last_event_per_store: dict
    stale_feeds: List[str]
    uptime_seconds: float
    db_status: str
