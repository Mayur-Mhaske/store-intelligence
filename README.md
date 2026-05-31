# Store Intelligence System
### Purplle Tech Challenge 2026 — Round 2
### Brigade Bangalore Store (ST1008)

---

## Setup in 5 Commands

```bash
# 1. Go to app folder
cd app

# 2. Install dependencies
pip install fastapi uvicorn sqlalchemy pydantic structlog pytest httpx requests

# 3. Start API
uvicorn main:app --reload --port 8000

# 4. Generate mock events (new terminal)
cd ../pipeline
python generate_mock_events.py --visitors 60 --output ../events_output/mock.jsonl
python -c "from emit import replay_to_api; replay_to_api('../events_output/mock.jsonl')"

# 5. Check metrics
curl http://localhost:8000/stores/ST1008/metrics
```

> API Docs: http://localhost:8000/docs

---

## Run Detection on Real CCTV Clips

```bash
cd pipeline

# Single clip
python detect.py --video "C:/Users/Admin/Desktop/CCTV Footage/CAM 1.mp4" --camera CAM_1 --output ../events_output/CAM_1.jsonl

# All 5 clips
python run_all.py --footage "C:/Users/Admin/Desktop/CCTV Footage" --api http://localhost:8000
```

---

## Run Dashboard

```bash
cd dashboard
npm install
npm start
# Opens at http://localhost:3000
```

---

## Run Tests

```bash
cd tests
pytest test_pipeline.py test_metrics.py test_anomalies.py -v
```

---

## Run Assertions

```bash
# API must be running first
python assertions.py
```

---

## Docker (Production)

```bash
docker compose up --build
```

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `POST /events/ingest` | Ingest up to 500 events (idempotent) |
| `GET /stores/ST1008/metrics` | Visitors, conversion, dwell, queue |
| `GET /stores/ST1008/funnel` | Entry → Zone → Billing → Purchase |
| `GET /stores/ST1008/heatmap` | Zone heatmap 0–100 normalized |
| `GET /stores/ST1008/anomalies` | Active anomalies with severity |
| `GET /health` | Service health + stale feeds |

---

## Store Details

- **Store:** Brigade Bangalore
- **Store ID:** ST1008
- **Zones:** SKIN, HAIR, FRAGRANCE, MAKEUP, PERSONAL_CARE, BATH_BODY, OFFERS, BILLING
- **Cameras:** 5 (Entry x2, Floor x2, Billing x1)
- **POS Data:** 24 real transactions from 10-Apr-2026

---

## Tech Stack

| Layer | Technology |
|---|---|
| Detection | YOLOv8-nano + ByteTrack |
| API | FastAPI + SQLite |
| Dashboard | React + Recharts |
| Tests | pytest (3 files) |
| Container | Docker Compose |
