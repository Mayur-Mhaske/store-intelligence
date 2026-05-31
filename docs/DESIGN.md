# DESIGN.md — Store Intelligence System
## Purplle Tech Challenge 2026 | Round 2
## Brigade Bangalore Store (ST1008)

---

## Architecture Overview

End-to-end pipeline: raw CCTV footage → AI detection → structured events → REST API → live dashboard.

```
CCTV Clips (5 cameras) → YOLOv8n + ByteTrack → Structured Events (JSONL)
                                                          ↓
React Dashboard ← FastAPI (port 8000) ← SQLite ← POST /events/ingest
```

---

## Stage 1 — Detection Layer

**Model:** YOLOv8-nano (CPU optimized)
- Class 0 (person) detection, confidence threshold 0.35
- Frame skipping every 3rd frame for CPU performance (3x speed gain)
- ByteTrack multi-object tracking with Kalman filter for occlusion handling

**Store:** Brigade Bangalore (ST1008) — 5 cameras, 6 product zones + billing

**Zone Mapping:** Pixel coordinates → normalized ratios (0–1) → matched against store_layout.json zone boundaries. Zones: SKIN, HAIR, FRAGRANCE, MAKEUP, PERSONAL_CARE, BATH_BODY, OFFERS, BILLING.

**Edge Cases Handled:**
| Edge Case | Approach |
|---|---|
| Group entry | YOLOv8 detects individuals — 3 people = 3 bounding boxes = 3 ENTRY events |
| Staff detection | HSV color analysis on bounding box ROI — blue uniform >20% → is_staff=True |
| Re-entry | Spatial proximity (<150px) + temporal window (<300s) → REENTRY event |
| Partial occlusion | ByteTrack Kalman filter maintains track through occlusion |
| Empty periods | API returns zero-value responses, never null or crash |
| Camera overlap | Same visitor_id across cameras prevents double-counting |

---

## Stage 2 — Event Schema

8 event types as per problem statement. Key design decisions:
- `confidence` always emitted — low-confidence events flagged, never suppressed
- `is_staff` on every event — flexible downstream filtering
- `session_seq` enables session reconstruction
- `sanitize_event()` converts numpy types to Python types before JSON serialization

---

## Stage 3 — Intelligence API

**Framework:** FastAPI — scoring harness optimized for it, Pydantic v2 auto-validation

**Storage:** SQLite — no Docker overhead on Windows, sufficient for 5-camera hackathon scale

**POS Correlation:** Conversion rate computed by matching billing zone visitors to POS transactions within 5-minute window — exactly as specified in problem statement.

**Idempotency:** event_id UUID deduplication on every ingest — network retries safe

**Graceful degradation:** DB unavailable → HTTP 503 structured response, no raw stack traces

---

## Stage 4 — Dashboard

React with 5-second polling. Shows KPIs (visitors, conversion, queue, abandonment), zone heatmap, conversion funnel, active anomalies, dwell table.

---

## AI-Assisted Decisions

### 1. ByteTrack vs DeepSORT
Claude suggested ByteTrack for crowded retail scenes — its BYTE algorithm uses both high and low confidence detections, better for partial occlusion. I agreed and used it.

### 2. Re-ID Strategy
Claude suggested OSNet (torchreid) for appearance-based Re-ID. I overrode this — OSNet requires GPU and adds significant complexity. Spatial proximity + temporal window works well on CPU for the 5-minute re-entry window defined in the problem statement.

### 3. Confidence Threshold
Claude initially suggested dropping events below 0.5 confidence. I disagreed — problem statement explicitly says "do not suppress low-conf events, flag them instead." Kept all events with confidence field populated.

---

## POS Correlation Logic

The problem statement specifies that a visitor in the billing zone within the 5-minute window before a POS transaction counts as a converted visitor for that session. This is implemented in `metrics.py` via `get_converted_visitors()`:

1. Load all POS transactions for the store within the query window from `pos_transactions.csv`
2. For each transaction, compute a 5-minute look-back window
3. Query the events database for distinct visitor_ids in the BILLING zone within that window
4. Union all such visitor_ids across all transactions — this is the converted set
5. Conversion rate = converted / unique_visitors × 100

This approach correctly handles the case where one visitor may have triggered multiple transactions (e.g., split billing), counting them only once via the set union.

---

## Observability

Every HTTP request is logged as structured JSON with the following fields:
- `trace_id` — UUID generated per request for distributed tracing
- `endpoint` — the route path
- `method` — HTTP method
- `status_code` — response code
- `latency_ms` — end-to-end response time
- `store_id` — extracted from path params where applicable

The `/health` endpoint provides operational visibility: DB connectivity, last event timestamp per store, stale feed detection (>10 min lag), and API uptime. This is the first endpoint an on-call engineer checks.

---

## Error Handling Strategy

- **DB unavailable** → HTTP 503 with structured JSON body, no raw stack traces exposed
- **Malformed events** → Partial success — valid events accepted, malformed events rejected with per-event error detail
- **Empty store** → Zero-value responses (not null, not 500) — explicitly tested
- **Re-entry edge case** → Spatial + temporal heuristic degrades gracefully when track_id reappears near exit point
