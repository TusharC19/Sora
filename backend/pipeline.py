import cv2
import math
import os
from typing import List, Dict, Any
from ultralytics import YOLO

# Common classes we care about in incident forensics (COCO class IDs)
# 0: person, 24: backpack, 26: handbag, 28: suitcase, 63: laptop, 67: cell phone, 73: book
TRACKED_OBJECTS = {
    0: "person",
    24: "backpack",
    26: "handbag",
    28: "suitcase",
    39: "bottle",
    63: "laptop",
    67: "cell phone",
    73: "book"
}

def format_timestamp(seconds: float) -> str:
    """Convert float seconds to MM:SS string."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"

def calculate_distance(box1: List[float], box2: List[float]) -> float:
    """Calculate Euclidean distance between the centers of two bounding boxes [x1, y1, x2, y2]."""
    c1_x = (box1[0] + box1[2]) / 2.0
    c1_y = (box1[1] + box1[3]) / 2.0
    c2_x = (box2[0] + box2[2]) / 2.0
    c2_y = (box2[1] + box2[3]) / 2.0
    return math.sqrt((c1_x - c2_x) ** 2 + (c1_y - c2_y) ** 2)

class VideoIntelligenceEngine:
    def __init__(self, model_name: str = "yolov8n.pt"):
        """Initialize the YOLO model (lightweight, runs smoothly on CPU)."""
        print(f"[SORA] Loading model: {model_name}...")
        self.model = YOLO(model_name)
        print("[SORA] Model loaded successfully.")

    def process_video(self, video_path: str, sample_rate_seconds: float = 1.0) -> Dict[str, Any]:
        """
        Process a video file, sample frames at regular intervals, track objects,
        and generate a high-level chronological event timeline.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps

        frame_step = max(1, int(fps * sample_rate_seconds))
        print(f"[SORA] Analyzing '{video_path}' | Duration: {format_timestamp(duration)} | FPS: {fps:.1f} | Step: every {sample_rate_seconds}s")

        events: List[Dict[str, Any]] = []
        active_persons = set()
        person_near_objects = set()  # (person_id, obj_name) to avoid spamming the log

        frame_idx = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_step == 0:
                current_time = frame_idx / fps
                time_str = format_timestamp(current_time)

                # Run YOLO tracking with ByteTrack
                results = self.model.track(frame, persist=True, verbose=False)
                
                current_frame_persons = set()
                person_boxes = {}
                item_boxes = []

                if results and len(results) > 0 and results[0].boxes is not None:
                    boxes = results[0].boxes
                    
                    for i in range(len(boxes)):
                        cls_id = int(boxes.cls[i].item())
                        conf = float(boxes.conf[i].item())
                        
                        # Only consider high-confidence detections of items we care about
                        if conf < 0.45 or cls_id not in TRACKED_OBJECTS:
                            continue

                        box_coords = boxes.xyxy[i].tolist()
                        track_id = int(boxes.id[i].item()) if boxes.id is not None and boxes.id[i] is not None else None
                        obj_type = TRACKED_OBJECTS[cls_id]

                        if obj_type == "person":
                            pid = track_id or f"p_{i}"
                            current_frame_persons.add(pid)
                            person_boxes[pid] = box_coords
                        else:
                            item_boxes.append((obj_type, box_coords))

                # Event 1: New person enters
                new_arrivals = current_frame_persons - active_persons
                for pid in new_arrivals:
                    events.append({
                        "timestamp": time_str,
                        "time_seconds": round(current_time, 2),
                        "type": "PERSON_ENTERED",
                        "description": f"Person (ID: {pid}) entered the monitored area.",
                        "subject": f"Person #{pid}",
                        "severity": "info"
                    })

                # Event 2: Person exits
                departures = active_persons - current_frame_persons
                for pid in departures:
                    events.append({
                        "timestamp": time_str,
                        "time_seconds": round(current_time, 2),
                        "type": "PERSON_EXITED",
                        "description": f"Person (ID: {pid}) exited the monitored area.",
                        "subject": f"Person #{pid}",
                        "severity": "info"
                    })

                # Event 3: Proximity / Interaction (Person approaching an item like laptop/bag)
                for pid, p_box in person_boxes.items():
                    p_width = abs(p_box[2] - p_box[0])
                    threshold_distance = max(80.0, p_width * 1.2)

                    for item_name, i_box in item_boxes:
                        dist = calculate_distance(p_box, i_box)
                        pair_key = (pid, item_name)

                        if dist < threshold_distance:
                            if pair_key not in person_near_objects:
                                person_near_objects.add(pair_key)
                                events.append({
                                    "timestamp": time_str,
                                    "time_seconds": round(current_time, 2),
                                    "type": "OBJECT_INTERACTION",
                                    "description": f"Person (ID: {pid}) approached {item_name}.",
                                    "subject": item_name,
                                    "severity": "warning"
                                })
                        else:
                            # Reset proximity if they stepped away
                            if pair_key in person_near_objects:
                                person_near_objects.remove(pair_key)

                active_persons = current_frame_persons

            frame_idx += 1

        cap.release()
        print(f"[SORA] Extraction complete. Generated {len(events)} structured events.")

        return {
            "video_path": video_path,
            "duration_seconds": round(duration, 2),
            "duration_formatted": format_timestamp(duration),
            "total_events": len(events),
            "events": events
        }
