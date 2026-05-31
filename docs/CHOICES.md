# CHOICES.md — Architecture Decision Record
## Purplle Tech Challenge 2026 | Round 2

---

## Decision 1 — Detection Model: YOLOv8-nano

### Options Considered
| Model | CPU Speed | Accuracy | Decision |
|---|---|---|---|
| YOLOv8-nano | ✅ Fastest | Good | ✅ Chosen |
| YOLOv8-medium | Medium | Better | ❌ Too slow on CPU |
| YOLOv8-large | Slow | Best | ❌ GPU required |
| RT-DETR | Very slow | Excellent | ❌ Not feasible CPU |
| MediaPipe | Fast | Limited | ❌ Not for crowds |

### What AI Suggested
Claude suggested YOLOv8-medium for better accuracy at 1080p. Also mentioned RT-DETR as strong for crowded billing areas.

### What I Chose and Why
YOLOv8-nano — no GPU available. ByteTrack compensates for lower per-frame accuracy by maintaining track continuity across frames. Frame skipping (every 3rd frame) gives 3x CPU speedup without significant accuracy loss at 30fps. For billing area occlusion, ByteTrack's Kalman filter handles it better than a more accurate single-frame detector without tracking.

---

## Decision 2 — Event Schema: Unified vs Per-Type

### Options Considered
- **Option A:** Unified schema — all events same format, optional fields null when unused
- **Option B:** Discriminated union — different Pydantic model per event type
- **Option C:** Flat schema — all fields at root, no metadata nesting

### What AI Suggested
Claude suggested Option B (discriminated union) for type safety — ENTRY events don't need zone_id, BILLING_QUEUE_JOIN always needs queue_depth. Showed implementation with Pydantic Literal types.

### What I Chose and Why
Option A (unified schema) — problem statement provided one schema with optional fields. Deviating risked automated test failures. Single schema = simpler ingestion, validation, and querying. `confidence` always included per problem statement requirement "do not suppress low-conf events." I adopted Claude's suggestion to always include session_seq for session reconstruction.

---

## Decision 3 — Storage: SQLite vs PostgreSQL

### Options Considered
| Engine | Setup | Concurrency | Scale |
|---|---|---|---|
| SQLite | Zero | Single-writer | ✅ Fine for hackathon |
| PostgreSQL | Docker required | Multi-writer | Production-ready |
| TimescaleDB | Docker + extension | Time-series optimized | Overkill for scale |

### What AI Suggested
Claude suggested TimescaleDB — events are pure time-series data, hypertable partitioning and time_bucket queries would be efficient. PostgreSQL as safe middle ground.

### What I Chose and Why
SQLite — no Docker Desktop required on Windows, acceptance gate is `docker compose up` which still works (SQLite file created inside container). Event volume for 5 cameras × ~2.5 minutes is well within SQLite's range. Indexes on (store_id, timestamp) and visitor_id give sub-millisecond queries at this scale. I adopted Claude's suggestion of composite indexing — significantly improved funnel and metrics query performance.

**Production upgrade path:** PostgreSQL → TimescaleDB as stores scale to 40+ with real-time feeds.

---

## Additional Engineering Decisions

### Conversion Rate Computation — POS Correlation vs Event-only

**Options Considered:**
- **Option A:** Count BILLING_QUEUE_JOIN minus BILLING_QUEUE_ABANDON as conversions — simple but inaccurate
- **Option B:** Correlate with actual POS transactions via 5-minute time window — exactly as problem statement specifies

**What AI Suggested:**
Claude suggested Option A for simplicity, noting POS correlation adds file I/O on every metrics request.

**What I Chose and Why:**
Option B — the problem statement explicitly defines conversion rate using POS correlation. Using Option A would produce inflated conversion rates since queue joins don't always mean purchases. The 5-minute window is loaded once per request and the file is small (24 transactions) so performance impact is negligible at this scale.

---

### Frame Skip Strategy — Every 3rd Frame vs Every Frame

**Options Considered:**
- **Process every frame** — maximum accuracy, very slow on CPU (1-2 fps)
- **Skip every 3rd frame** — 3x speedup, minimal accuracy loss at 30fps
- **Skip every 5th frame** — faster but tracking may lose persons in fast movement

**What AI Suggested:**
Claude suggested processing every frame for maximum detection accuracy, especially for the billing area where people move slowly.

**What I Chose and Why:**
Every 3rd frame — at 30fps, skipping 2 frames means we still process 10 frames per second. ByteTrack's Kalman filter interpolates positions between processed frames, so tracking continuity is maintained. The 3x speed improvement makes the pipeline practically runnable on CPU within the challenge window.

---

### Anomaly Detection — Rule-based vs ML-based

**Options Considered:**
- **Rule-based thresholds** — simple, explainable, no training data needed
- **Statistical anomaly detection** — z-score or IQR based
- **ML-based** — isolation forest or similar

**What AI Suggested:**
Claude suggested z-score based anomaly detection for conversion drop — more statistically rigorous than hard thresholds.

**What I Chose and Why:**
Rule-based thresholds — the problem statement explicitly defines the anomaly types and their conditions (queue >= threshold, conversion drop >= 15%/30%, dead zone after 30 min). Rule-based is more explainable in a follow-up interview and doesn't require historical training data. If 7-day history is insufficient, the system gracefully returns no CONVERSION_DROP anomaly rather than producing false positives.
