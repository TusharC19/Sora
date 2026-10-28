import json
import os
import shutil
import uuid
from typing import Optional
from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import google.generativeai as genai

from pipeline import VideoIntelligenceEngine

app = FastAPI(title="SORA - Searchable Observation & Reasoning Assistant")

# Enable CORS for React frontend (localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# Lazy-load engine so server starts quickly
engine = None

def get_engine():
    global engine
    if engine is None:
        engine = VideoIntelligenceEngine()
    return engine

class AskRequest(BaseModel):
    video_id: str
    question: str
    gemini_api_key: Optional[str] = None

@app.get("/")
def read_root():
    return {
        "status": "online",
        "app": "SORA - AI Video Intelligence & Forensics",
        "endpoints": ["/api/upload", "/api/process/{video_id}", "/api/events/{video_id}", "/api/ask"]
    }

@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    """Upload a video file (.mp4, .mov, .avi) to local storage."""
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in [".mp4", ".mov", ".avi", ".mkv", ".webm"]:
        raise HTTPException(status_code=400, detail="Unsupported video format. Please upload an MP4, MOV, or WEBM file.")

    video_id = str(uuid.uuid4())[:8]
    filename = f"{video_id}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "video_id": video_id,
        "filename": file.filename,
        "saved_path": file_path,
        "status": "uploaded"
    }

@app.post("/api/process/{video_id}")
def process_video(video_id: str, sample_rate: float = Query(1.0, ge=0.2, le=5.0)):
    """Analyze the uploaded video with YOLO & tracking, producing structured event timeline."""
    matched_files = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(video_id)]
    if not matched_files:
        raise HTTPException(status_code=404, detail="Video ID not found.")

    video_path = os.path.join(UPLOAD_DIR, matched_files[0])
    
    eng = get_engine()
    results = eng.process_video(video_path, sample_rate_seconds=sample_rate)
    results["video_id"] = video_id
    results["filename"] = matched_files[0]

    # Save structured event data to disk
    json_path = os.path.join(DATA_DIR, f"{video_id}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    return results

@app.get("/api/events/{video_id}")
def get_events(video_id: str):
    """Retrieve pre-extracted events for a video."""
    json_path = os.path.join(DATA_DIR, f"{video_id}.json")
    if not os.path.exists(json_path):
        raise HTTPException(status_code=404, detail="Analysis data not found. Please process the video first.")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data

@app.get("/api/video/{video_id}")
def stream_video(video_id: str):
    """Serve video directly for playback with seeking support."""
    matched_files = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(video_id)]
    if not matched_files:
        raise HTTPException(status_code=404, detail="Video file not found.")

    video_path = os.path.join(UPLOAD_DIR, matched_files[0])
    return FileResponse(video_path, media_type="video/mp4")

@app.post("/api/ask")
def ask_sora(payload: AskRequest):
    """Ask natural language questions about the video, backed by timestamped evidence."""
    json_path = os.path.join(DATA_DIR, f"{payload.video_id}.json")
    if not os.path.exists(json_path):
        raise HTTPException(status_code=404, detail="Video not analyzed yet. Run analysis first.")

    with open(json_path, "r", encoding="utf-8") as f:
        analysis_data = json.load(f)

    events = analysis_data.get("events", [])
    if not events:
        return {
            "answer": "No events were detected in this video segment.",
            "evidence": []
        }

    # Format events into a concise string for LLM reasoning
    event_summary_lines = [
        f"[{e['timestamp']}] {e['type']}: {e['description']}"
        for e in events
    ]
    events_text = "\n".join(event_summary_lines)

    # If Gemini API key is provided, use Google's free Gemini API
    api_key = payload.gemini_api_key or os.getenv("GEMINI_API_KEY")

    if api_key:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")

            prompt = f"""You are SORA, an AI video forensic assistant.
A user is asking a question about a surveillance/security video.
You MUST base your answer ONLY on the structured event log below.
Whenever you mention an event or finding, include the exact timestamp in brackets like [MM:SS].

Structured Video Event Log:
{events_text}

User Question: {payload.question}

Answer concisely, citing exact timestamps:"""

            response = model.generate_content(prompt)
            answer_text = response.text.strip()
            
            # Extract evidence timestamps
            evidence = [e["timestamp"] for e in events if e["timestamp"] in answer_text]

            return {
                "answer": answer_text,
                "evidence": list(set(evidence))
            }
        except Exception as e:
            print(f"[SORA] Gemini error: {e}. Falling back to keyword search.")

    # Smart local fallback if no Gemini key is provided
    q_lower = payload.question.lower()
    matching_events = []

    for e in events:
        desc_lower = e["description"].lower()
        sub_lower = e.get("subject", "").lower()
        if any(word in desc_lower or word in sub_lower for word in q_lower.split() if len(word) > 3):
            matching_events.append(e)

    if not matching_events:
        return {
            "answer": f"I analyzed the video events, but couldn't find a direct match for '{payload.question}'. You can review the chronological timeline cards.",
            "evidence": []
        }

    citations = [e["timestamp"] for e in matching_events]
    bullet_points = "\n".join([f"- At [{e['timestamp']}]: {e['description']}" for e in matching_events[:4]])
    
    answer = f"Based on the video event log:\n{bullet_points}"

    return {
        "answer": answer,
        "evidence": list(set(citations))
    }
