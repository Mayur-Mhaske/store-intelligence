"""
detect.py — Main Detection Pipeline
YOLOv8-nano + ByteTrack — CPU optimized for Windows
Brigade Bangalore Store (ST1008)

Usage:
    python detect.py --video "C:/path/CAM 1.mp4" --camera CAM_1 --output ../events_output/CAM_1.jsonl
"""

import cv2, json, uuid, argparse, os
from datetime import datetime, timedelta
import numpy as np
from ultralytics import YOLO
from tracker import VisitorTracker
from emit import EventEmitter

STORE_ID = "ST1008"
MODEL_SIZE = "yolov8n.pt"
CONFIDENCE_THRESHOLD = 0.35
ENTRY_LINE_RATIO = 0.45
SKIP_FRAMES = 3
STAFF_BLUE_LOWER = np.array([100, 50, 50])
STAFF_BLUE_UPPER = np.array([130, 255, 255])

LAYOUT_PATH = os.path.join(os.path.dirname(__file__), "..", "store_layout.json")


def get_zone(cx, cy, fw, fh):
    xr = cx / fw
    yr = cy / fh
    try:
        with open(LAYOUT_PATH) as f:
            layout = json.load(f)
        zones = layout["stores"][0]["zones"]
        for zone in zones:
            if zone["x1"] <= xr < zone["x2"] and zone["y1"] <= yr < zone["y2"]:
                return zone["zone_id"]
    except Exception:
        pass
    return "MAKEUP"


def detect_staff(frame, bbox):
    x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
    x1, y1 = max(0, x1), max(0, y1)
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return False
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, STAFF_BLUE_LOWER, STAFF_BLUE_UPPER)
    ratio = np.sum(mask > 0) / (roi.shape[0] * roi.shape[1] + 1e-5)
    return bool(ratio > 0.20)


def sanitize(e):
    return {
        "event_id": str(e["event_id"]),
        "store_id": str(e["store_id"]),
        "camera_id": str(e["camera_id"]),
        "visitor_id": str(e["visitor_id"]),
        "event_type": str(e["event_type"]),
        "timestamp": str(e["timestamp"]),
        "zone_id": str(e["zone_id"]) if e.get("zone_id") is not None else None,
        "dwell_ms": int(e.get("dwell_ms", 0)),
        "is_staff": bool(e.get("is_staff", False)),
        "confidence": float(round(e.get("confidence", 0.0), 4)),
        "metadata": {
            "queue_depth": int(e["metadata"]["queue_depth"]) if e["metadata"].get("queue_depth") is not None else None,
            "sku_zone": str(e["metadata"]["sku_zone"]) if e["metadata"].get("sku_zone") is not None else None,
            "session_seq": int(e["metadata"].get("session_seq", 1))
        }
    }


class DetectionPipeline:
    def __init__(self, camera_id, clip_start):
        self.camera_id = camera_id
        self.clip_start = clip_start
        print(f"Loading YOLOv8 model ({MODEL_SIZE})...")
        self.model = YOLO(MODEL_SIZE)
        self.tracker = VisitorTracker()
        self.emitter = EventEmitter(STORE_ID, camera_id)
        print("Model loaded!")

    def frame_to_ts(self, frame_num, fps):
        return self.clip_start + timedelta(seconds=frame_num / fps)

    def process(self, video_path, output_path):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open: {video_path}")

        fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        entry_y = int(fh * ENTRY_LINE_RATIO)

        print(f"\nProcessing: {video_path}")
        print(f"Resolution: {fw}x{fh} @ {fps:.1f}fps | Frames: {total_frames}")
        print(f"Entry line Y: {entry_y}px\n")

        events = []
        frame_num = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_num += 1
            if frame_num % SKIP_FRAMES != 0:
                continue

            ts = self.frame_to_ts(frame_num, fps)
            results = self.model.track(frame, persist=True, classes=[0],
                                       conf=CONFIDENCE_THRESHOLD, tracker="bytetrack.yaml", verbose=False)

            if results and results[0].boxes is not None:
                for box in results[0].boxes:
                    if box.id is None:
                        continue
                    track_id = int(box.id.item())
                    conf = float(box.conf.item())
                    bbox = box.xyxy[0].tolist()
                    cx = float((bbox[0] + bbox[2]) / 2)
                    cy = float((bbox[1] + bbox[3]) / 2)
                    is_staff = bool(detect_staff(frame, bbox))
                    zone_id = get_zone(cx, cy, fw, fh)

                    track_events = self.tracker.update(track_id, cx, cy, zone_id, is_staff, conf, ts, entry_y, fh)

                    for event_type, extra in track_events:
                        visitor_id = self.tracker.get_visitor_id(track_id)
                        event = self.emitter.emit(
                            event_type=event_type,
                            visitor_id=visitor_id,
                            timestamp=ts,
                            zone_id=zone_id if event_type not in ["ENTRY", "EXIT", "REENTRY"] else None,
                            is_staff=is_staff,
                            confidence=conf,
                            extra=extra
                        )
                        events.append(event)

            if frame_num % 100 == 0:
                pct = (frame_num / total_frames * 100) if total_frames > 0 else 0
                print(f"  Frame {frame_num}/{total_frames} ({pct:.1f}%) — Events: {len(events)}")

        cap.release()
        exit_events = self.tracker.flush_exits(self.frame_to_ts(frame_num, fps))
        events.extend(exit_events)

        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
        with open(output_path, "w") as f:
            for e in events:
                f.write(json.dumps(sanitize(e)) + "\n")

        print(f"\n✅ Done! {len(events)} events → {output_path}")
        return events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--camera", default="CAM_1")
    parser.add_argument("--output", default="../events_output/output.jsonl")
    parser.add_argument("--clip-start", default="2026-04-10T10:00:00")
    args = parser.parse_args()
    clip_start = datetime.fromisoformat(args.clip_start)
    pipeline = DetectionPipeline(camera_id=args.camera, clip_start=clip_start)
    pipeline.process(args.video, args.output)


if __name__ == "__main__":
    main()
