"""
run_all.py — Process all 5 CCTV clips → API
Usage: python run_all.py --footage "C:/Users/Admin/Desktop/CCTV Footage" --api http://localhost:8000
"""
import os, argparse, subprocess, sys
from emit import replay_to_api

CAMERA_MAP = {"CAM 1": "CAM_1", "CAM 2": "CAM_2", "CAM 3": "CAM_3", "CAM 4": "CAM_4", "CAM 5": "CAM_5"}
CLIP_START = "2026-04-10T10:00:00"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--footage", required=True)
    parser.add_argument("--api", default="http://localhost:8000")
    args = parser.parse_args()

    events_dir = os.path.join(os.path.dirname(__file__), "..", "events_output")
    os.makedirs(events_dir, exist_ok=True)

    print("=" * 50)
    print("  Store Intelligence — Brigade Bangalore (ST1008)")
    print("=" * 50)

    for cam_name, cam_id in CAMERA_MAP.items():
        video_path = None
        for ext in [".mp4", ".MP4", ".avi"]:
            candidate = os.path.join(args.footage, cam_name + ext)
            if os.path.exists(candidate):
                video_path = candidate
                break

        if not video_path:
            print(f"\n⚠️  {cam_name} not found — skipping")
            continue

        output_path = os.path.join(events_dir, f"{cam_id}.jsonl")
        print(f"\n📹 Processing {cam_name} → {cam_id}")

        cmd = [sys.executable,
               os.path.join(os.path.dirname(__file__), "detect.py"),
               "--video", video_path,
               "--camera", cam_id,
               "--output", output_path,
               "--clip-start", CLIP_START]

        result = subprocess.run(cmd, cwd=os.path.dirname(__file__))

        if result.returncode == 0 and os.path.exists(output_path):
            print(f"⬆️  Sending events to API...")
            replay_to_api(output_path, args.api)
        else:
            print(f"❌ Detection failed for {cam_name}")

    print("\n" + "=" * 50)
    print("✅ All clips processed!")
    print(f"📊 Dashboard: http://localhost:3000")
    print(f"📖 API Docs:  {args.api}/docs")
    print("=" * 50)


if __name__ == "__main__":
    main()
