from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
import structlog, uuid, time

from database import get_db, create_tables
from models import EventBatch, IngestResponse, StoreMetrics, StoreFunnel, StoreHeatmap, HealthStatus
from ingestion import ingest_events
from metrics import get_store_metrics, get_store_heatmap
from funnel import get_store_funnel
from anomalies import detect_anomalies
from health import get_health

structlog.configure(processors=[
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.stdlib.add_log_level,
    structlog.processors.JSONRenderer()
])
logger = structlog.get_logger()

app = FastAPI(title="Store Intelligence API", version="1.0.0",
              description="Purplle Tech Challenge 2026 — Brigade Bangalore Store Analytics")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup():
    create_tables()
    logger.info("api_started", version="1.0.0", store="ST1008")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    trace_id = str(uuid.uuid4())
    start = time.time()
    response = await call_next(request)
    logger.info("request",
        trace_id=trace_id,
        endpoint=str(request.url.path),
        method=request.method,
        status_code=response.status_code,
        latency_ms=round((time.time() - start) * 1000, 2),
        store_id=request.path_params.get("store_id")
    )
    response.headers["X-Trace-Id"] = trace_id
    return response


@app.exception_handler(OperationalError)
async def db_error(request: Request, exc: OperationalError):
    return JSONResponse(status_code=503, content={
        "error": "Service temporarily unavailable",
        "detail": "Database connection failed"
    })


@app.post("/events/ingest", response_model=IngestResponse)
def ingest(batch: EventBatch, db: Session = Depends(get_db)):
    """Ingest up to 500 events. Idempotent by event_id. Partial success on errors."""
    return ingest_events(batch, db)


@app.get("/stores/{store_id}/metrics", response_model=StoreMetrics)
def metrics(store_id: str, hours: int = 24, db: Session = Depends(get_db)):
    """Real-time store metrics with POS-correlated conversion rate."""
    return get_store_metrics(store_id, db, hours)


@app.get("/stores/{store_id}/funnel", response_model=StoreFunnel)
def funnel(store_id: str, hours: int = 24, db: Session = Depends(get_db)):
    """Conversion funnel: Entry → Zone → Billing → Purchase. No double counting."""
    return get_store_funnel(store_id, db, hours)


@app.get("/stores/{store_id}/heatmap", response_model=StoreHeatmap)
def heatmap(store_id: str, hours: int = 24, db: Session = Depends(get_db)):
    """Zone visit frequency + avg dwell, normalized 0-100."""
    return get_store_heatmap(store_id, db, hours)


@app.get("/stores/{store_id}/anomalies")
def anomalies(store_id: str, db: Session = Depends(get_db)):
    """Active anomalies: queue spike, conversion drop, dead zone, stale feed."""
    return detect_anomalies(store_id, db)


@app.get("/health", response_model=HealthStatus)
def health(db: Session = Depends(get_db)):
    """Service health: DB status, last event per store, stale feed detection."""
    return get_health(db)
