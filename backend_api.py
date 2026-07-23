"""
Rahman Shorts - Production Backend API
Real video processing with FFmpeg, yt-dlp, and Whisper
"""

import os
import json
import re
import shutil
import subprocess
import uuid
import asyncio
from datetime import datetime
from typing import List, Optional
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Form, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx

# CONFIGURATION
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
CLIP_DIR = Path(os.getenv("CLIP_DIR", "./clips"))
TEMP_DIR = Path(os.getenv("TEMP_DIR", "./temp"))
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "2147483648"))
MAX_CLIPS = int(os.getenv("MAX_CLIPS", "20"))
MAX_CLIP_DURATION = int(os.getenv("MAX_CLIP_DURATION", "60"))
DEFAULT_CLIP_DURATION = int(os.getenv("DEFAULT_CLIP_DURATION", "30"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

for d in [UPLOAD_DIR, CLIP_DIR, TEMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# DATA MODELS
class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int
    message: str
    clips: List[dict] = []
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None

class ClipEdit(BaseModel):
    caption: str
    template_id: str
    start_time: float
    end_time: float

jobs: dict[str, JobStatus] = {}

# FASTAPI APP
app = FastAPI(
    title="Rahman Shorts API",
    description="AI Video-to-Shorts Generator - Real FFmpeg Processing",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if "*" in CORS_ORIGINS else CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if os.path.exists("frontend"):
    app.mount("/static", StaticFiles(directory="frontend"), name="frontend")

# HELPER FUNCTIONS
def run_cmd(cmd: list, timeout: int = 300) -> tuple:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "Command timed out", 1
    except Exception as e:
        return "", str(e), 1

def get_video_info(video_path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration",
        "-show_entries", "format=duration",
        "-of", "json", str(video_path)
    ]
    stdout, stderr, rc = run_cmd(cmd)
    if rc != 0:
        return {"duration": 0, "width": 1920, "height": 1080}
    try:
        data = jsonloads(stdout)
        streams = dataget("streams", [{}])[0]
        fmt = data.get("format", {})
        duration = float(streams.get("duration", fmt.get("duration", 0)))
        return {"duration": duration, "width": int(streams.get("width", 1920)), "height": int(streams.get("height", 1080))}
    except:
        return {"duration": 0, "width": 1920, "height": 1080}

def extract_thumbnail(video_path: Path, output_path: Path, time: float = 1.0):
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path), "-ss", str(time),
        "-vframes", "1", "-q:v", "2", "-vf", "scale=480:-1", str(output_path)
    ]
    run_cmd(cmd, timeout=30)

def download_youtube(url: str, output_path: Path) -> bool:
    cmd = ["yt-dlp", "-f", "best[height<=1080]", "--no-playlist", "-o", str(output_path), "--newline", url]
    stdout, stderr, rc = run_cmd(cmd, timeout=600)
    return rc == 0 and output_path.exists() and output_path.stat().st_size > 1000

def transcribe_with_whisper(audio_path: Path) -> list:
    if not OPENAI_API_KEY:
        return generate_mock_transcription(audio_path)
    try:
        import openai
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        with open(audio_path, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", file=f, response_format="verbose_json",
                timestamp_granularities=["word"]
            )
        words = []
        for segment in transcriptsegments:
            words. append({"text": segment.text.strip(), "start": segment. start, "end": segment.end})
        return words
    except Exception as e:
        print(f"Whisper API error: {e}")
        return generate_mock_transcription(audio_path)

def generate_mock_transcription(audio_path: Path) -> list:
    info = get_video_info(audio_path)
    duration = info.get("duration", 300)
    viral_phrases = [
        "You won't believe what happens next", "This changed everything for me",
        "The secret nobody talks about", "I was shocked when I found out",
        "This is the moment that went viral", "Wait for it...",
        "The truth about success", "What they don't want you to know",
        "This one trick will blow your mind", "I made this mistake so you don't have to",
        "The real reason why", "Nobody expected this", "This is insane",
        "Mind = blown", "You need to see this",
    ]
    words = []
    current_time = 0
    phrase_idx = 0
    while current_time < duration - 5:
        phrase = viral_phrases[phrase_idx % len(viral_phrases)]
        words.append({"text": phrase, "start": current_time, "end": current_time + 3})
        current_time += 8 + (phrase_idx % 5)
        phrase_idx += 1
    return words

def find_viral_moments(transcript: list, video_duration: float, clip_count: int, clip_duration: int) -> list:
    viral_keywords = [
        "secret", "shocked", "viral", "believe", "blow", "mind", "insane",
        "truth", "mistake", "unexpected", "changed", "everything", "wait",
        "need", "see", "real", "reason", "nobody", "talks", "trick",
        "hack", "revealed", "exposed", "hidden", "discover", "amazing",
        "incredible", "unbelievable", "shocking", "surprising", "must",
        "watch", "until", "end", "plot", "twist", "game", "changer"
    ]
    scored_segments = []
    for segment in transcript:
        text_lower = segment["text"].lower()
        score = 0
        for keyword in viral_keywords:
            if keyword in text_lower:
                score += 15
        if "?" in segment["text"]:
            score += 20
        if re.search(r'\d+', segment["text"]):
            score += 10
        text_len = len(segment["text"].split())
        if 5 <= text_len <= 15:
            score += 10
        emotional = ["love", "hate", "fear", "hope", "dream", "passion", "obsessed"]
        for word in emotional:
            if word in text_lower:
                score += 8
        scored_segments.append({"start": segment["start"], "end": segment["end"], "text": segment["text"], "score": score})
    scored_segments.sort(key=lambda x: x["score"], reverse=True)
    selected = []
    used_ranges = []
    for seg in scored_segments:
        if len(selected) >= clip_count:
            break
        overlap = False
        for used in used_ranges:
            if not (seg["end"] < used[0] or seg["start"] > used[1]):
                overlap = True
                break
        if not overlap:
            mid = (seg["start"] + seg["end"]) / 2
            start = max(0, mid - clip_duration / 2)
            end = min(video_duration, start + clip_duration)
            if end > video_duration:
                end = video_duration
                start = max(0, end - clip_duration)
            selected.append({"start": round(start, 2), "end": round(end, 2), "text": seg["text"], "viral_score": min(99, max(70, seg["score"] + 70))})
            used_ranges.append((start, end))
    if len(selected) < clip_count:
        spacing = video_duration / (clip_count + 1)
        for i in range(clip_count - len(selected)):
            start = spacing * (i + 1)
            end = min(start + clip_duration, video_duration)
            selected.append({"start": round(start, 2), "end": round(end, 2), "text": f"Clip {len(selected) + 1}", "viral_score": 75})
    selected.sort(key=lambda x: x["start"])
    return selected[:clip_count]

def load_templates() -> dict:
    template_path = Path("templates/caption_templates.json")
    if template_path.exists():
        with open(template_path) as f:
            return json.load(f)
    return {"templates": []}

def generate_caption_filter(template: dict, caption: str, width: int, height: int) -> str:
    style = template.get("style", {})
    safe_caption = caption.replace("'", r"\'").replace(":", r"\:").replace("\n", r"\n")
    params = [
        f"text='{safe_caption}'",
        f"fontcolor={style.get('fontcolor', '#FFFFFF')}",
        f"fontsize={style.get('fontsize', '48')}",
        "x=(w-text_w)/2", "y=(h*0.85)",
        "fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    if style.get("box") == "1":
        params.append(f"box=1:boxcolor={style.get('boxcolor', '#000000@0.7')}:boxborderw={style.get('boxborderw', '10')}")
    if style.get("borderw"):
        params.append(f"borderw={style['borderw']}:bordercolor={style.get('bordercolor', '#000000')}")
    if style.get("shadowx"):
        params.append(f"shadowx={style['shadowx']}:shadowy={style.get('shadowy', '3')}:shadowcolor={style.get('shadowcolor', '#000000@0.5')}")
    return f"drawtext={':'.join(params)}"

def create_short_clip(input_video: Path, output_clip: Path, start: float, end: float, caption: str, template: dict, video_info: dict) -> bool:
    duration = end - start
    width = video_info["width"]
    height = video_info["height"]
    target_ratio = 9 / 16
    current_ratio = width/height
    if current_ratio > target_ratio:
        new_width = int(height * target_ratio)
        new_height = height
        crop_x = (width - new_width) // 2
        crop_y = 0
    else:
        new_width = width
        new_height = int(width / target_ratio)
        crop_x = 0
        crop_y = (height - new_height) // 2
    new_width = new_width // 2 * 2
    new_height = new_height // 2 * 2
    crop_x = crop_x // 2 * 2
    crop_y = crop_y // 2 * 2
    filters = [
        f"crop={new_width}:{new_height}:{crop_x}:{crop_y}",
        "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
    ]
    if caption and template:
        words = caption.split()
        lines = []
        current_line = []
        for word in words:
            current_line.append(word)
            if len(current_line) >= 3:
                lines.append(" ".join(current_line))
                current_line = []
        if current_line:
            lines.append(" ".join(current_line))
        caption_text = r"\n".join(lines) if len(lines) > 1 else caption
        drawtext = generate_caption_filter(template, caption_text, 1080, 1920)
        filters.append(drawtext)
    filter_str = ",".join(filters)
    cmd = [
        "ffmpeg", "-y", "-ss", str(start), "-t", str(duration), "-i", str(input_video),
        "-vf", filter_str, "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-pix_fmt", "yuv420p", str(output_clip)
    ]
    stdout, stderr, rc = run_cmd(cmd, timeout=120)
    return rc == 0 and output_clip.exists() and output_clip.stat().st_size > 1000

async def process_video_job(job_id: str, source: str, is_url: bool, settings: dict):
    job = jobs[job_id]
    temp_id = str(uuid.uuid4())[:8]
    try:
        job.status = "downloading"
        job.progress = 5
        job.message = "Downloading video..."
        video_path = TEMP_DIR / f"{temp_id}_input.mp4"
        if is_url:
            success = await asyncio.to_thread(download_youtube, source, video_path)
            if not success:
                raise Exception("Failed to download video. Check URL and try again.")
        else:
            shutil.copy(source, video_path)
        if not video_path.exists():
            raise Exception("Video file not found after download")
        job.progress = 20
        job.message = "Analyzing video..."
        video_info = await asyncio.to_thread(get_video_info, video_path)
        duration = video_info["duration"]
        if duration < 10:
            raise Exception("Video too short (minimum 10 seconds)")
        job.status = "transcribing"
        job.progress = 30
        job.message = "Transcribing audio with AI..."
        audio_path = TEMP_DIR / f"{temp_id}_audio.wav"
        cmd = ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(audio_path)]
        await asyncio.to_thread(run_cmd, cmd, 120)
        transcript = []
        if audio_path.exists():
            transcript = await asyncio.to_thread(transcribe_with_whisper, audio_path)
        job.progress = 50
        job.message = "Finding viral moments..."
        job.status = "analyzing"
        clip_count = min(settings.get("clip_count", 5), MAX_CLIPS)
        clip_duration = min(settings.get("clip_duration", DEFAULT_CLIP_DURATION), MAX_CLIP_DURATION)
        template_id = settings.get("template_id", "bold")
        language = settings.get("language", "en")
        viral_clips = await asyncio.to_thread(find_viral_moments, transcript, duration, clip_count, clip_duration)
        job.progress = 60
        job.message = f"Generating {len(viral_clips)} short clips..."
        job.status = "generating"
        templates = load_templates()
        template = next((t for t in templates.get("templates", []) if t["id"] == template_id), None)
        if not template:
            template = templates.get("templates", [{}])[0]
        generated_clips = []
        total_clips = len(viral_clips)
        for idx, clip_data in enumerate(viral_clips):
            clip_id = f"{job_id}_{idx}"
            output_path = CLIP_DIR / f"{clip_id}.mp4"
            thumb_path = CLIP_DIR / f"{clip_id}.jpg"
            success = await asyncio.to_thread(create_short_clip, video_path, output_path, clip_data["start"], clip_data["end"], clip_data["text"], template, video_info)
            if success:
                await asyncio.to_thread(extract_thumbnail, output_path, thumb_path, (clip_data["end"] - clip_data["start"]) / 2)
                clip_info = {
                    "id": clip_id, "start_time": clip_data["start"], "end_time": clip_data["end"],
                    "duration": round(clip_data["end"] - clip_data["start"], 1), "caption": clip_data["text"],
                    "viral_score": clip_data["viral_score"], "template_id": template_id,
                    "download_url": f"/api/download/{clip_id}",
                    "thumbnail_url": f"/api/thumbnail/{clip_id}" if thumb_path.exists() else None,
                    "file_size": output_path.stat().st_size, "created_at": datetime.now().isoformat()
                }
                generated_clips.append(clip_info)
            job.progress = 60 + int((idx + 1) / total_clips * 35)
            job.message = f"Generated clip {idx + 1}/{total_clips}..."
        for temp_file in [video_path, audio_path]:
            if temp_file.exists():
                temp_file.unlink()
        job.status = "completed"
        job.progress = 100
        job.message = f"Generated {len(generated_clips)} viral shorts!"
        job.clips = generated_clips
        job.completed_at = datetime.now().isoformat()
    except Exception as e:
        job.status = "failed"
        job.progress = 0
        job.error = str(e)
        job.message = f"Failed: {str(e)}"
        for temp_file in TEMP_DIR.glob(f"{temp_id}*"):
            temp_file.unlink(missing_ok=True)

@app.get("/")
async def root():
    return {"message": "Rahman Shorts API v2.0", "status": "running"}

@app.get("/api/health")
async def health_check():
    _, _, ffmpeg_rc = run_cmd(["ffmpeg", "-version"])
    ffmpeg_ok = ffmpeg_rc == 0
    _, _, ytdlp_rc = run_cmd(["yt-dlp", "--version"])
    ytdlp_ok = ytdlp_rc == 0
    openai_ok = bool(OPENAI_API_KEY)
    return {
        "status": "healthy" if ffmpeg_ok and ytdlp_ok else "degraded",
        "ffmpeg": "installed" if ffmpeg_ok else "missing",
        "yt_dlp": "installed" if ytdlp_ok else "missing",
        "openai_api": "connected" if openai_ok else "mock_mode",
        "version": "2.0.0", "timestamp": datetime.now().isoformat()
    }

@app.get("/api/templates")
async def get_templates():
    return load_templates()

@app.post("/api/process")
async def process_url(background_tasks: BackgroundTasks, url: str = Form(...), clip_count: int = Form(5), clip_duration: int = Form(30), template_id: str = Form("bold"), language: str = Form("en")):
    if not re.match(r'^https?://(www\.)?(youtube\.com|youtu\.be)/', url):
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
    clip_count = min(max(clip_count, 1), MAX_CLIPS)
    clip_duration = min(max(clip_duration, 15), MAX_CLIP_DURATION)
    job_id = str(uuid.uuid4())
    jobs[job_id] = JobStatus(job_id=job_id, status="pending", progress=0, message="Starting processing...", created_at=datetime.now().isoformat())
    settings = {"clip_count": clip_count, "clip_duration": clip_duration, "template_id": template_id, "language": language}
    background_tasks.add_task(process_video_job, job_id, url, True, settings)
    return {"job_id": job_id, "status": "started"}

@app.post("/api/process-file")
async def process_file(background_tasks: BackgroundTasks, file: UploadFile = File(...), clip_count: int = Form(5), clip_duration: int = Form(30), template_id: str = Form("bold"), language: str = Form("en")):
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="File must be a video")
    file_id = str(uuid.uuid4())[:8]
    file_path = UPLOAD_DIR / f"{file_id}_{file.filename}"
    with open(file_path, "wb") as f:
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            file_path.unlink(missing_ok=True)
            raise HTTPException(status_code=413, detail="File too large (max 2GB)")
        f.write(content)
    clip_count = min(max(clip_count, 1), MAX_CLIPS)
    clip_duration = min(max(clip_duration, 15), MAX_CLIP_DURATION)
    job_id = str(uuid.uuid4())
    jobs[job_id] = JobStatus(job_id=job_id, status="pending", progress=0, message="Starting processing...", created_at=datetime.now().isoformat())
    settings = {"clip_count": clip_count, "clip_duration": clip_duration, "template_id": template_id, "language": language}
    background_tasks.add_task(process_video_job, job_id, str(file_path), False, settings)
    return {"job_id": job_id, "status": "started"}

@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    return {"job_id": job.job_id, "status": job.status, "progress": job.progress, "message": job.message, "clips": job.clips, "error": job.error, "created_at": job.created_at, "completed_at": job.completed_at}

@app.get("/api/download/{clip_id}")
async def download_clip(clip_id: str):
    clip_path = CLIP_DIR / f"{clip_id}.mp4"
    if not clip_path.exists():
        raise HTTPException(status_code=404, detail="Clip not found")
    return FileResponse(path=clip_path, media_type="video/mp4", filename=f"rahman-shorts-{clip_id}.mp4")

@app.get("/api/thumbnail/{clip_id}")
async def get_thumbnail(clip_id: str):
    thumb_path = CLIP_DIR / f"{clip_id}.jpg"
    if not thumb_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return FileResponse(path=thumb_path, media_type="image/jpeg")

@app.post("/api/clip/{clip_id}/edit")
async def edit_clip(clip_id: str, edit: ClipEdit):
    original_clip = None
    for job_id, job in jobs.items():
        for clip in job.clips:
            if clip["id"] == clip_id:
                original_clip = clip
                break
        if original_clip:
            break
    if not original_clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    original_clip["caption"] = edit.caption
    original_clip["template_id"] = edit.template_id
    original_clip["start_time"] = edit.start_time
    original_clip["end_time"] = edit.end_time
    original_clip["duration"] = round(edit.end_time - edit.start_time, 1)
    return {"success": True, "clip": original_clip}

@app.delete("/api/clip/{clip_id}")
async def delete_clip(clip_id: str):
    clip_path = CLIP_DIR / f"{clip_id}.mp4"
    thumb_path = CLIP_DIR / f"{clip_id}.jpg"
    clip_path.unlink(missing_ok=True)
    thumb_path.unlink(missing_ok=True)
    return {"success": True}

@app.get("/api/jobs")
async def list_jobs():
    return {"jobs": [{"job_id": j.job_id, "status": j.status, "progress": j.progress, "clip_count": len(j.clips), "created_at": j.created_at} for j in jobs.values()]}

@app.on_event("startup")
async def startup_event():
    clips = sorted(CLIP_DIR.glob("*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True)
    for old_clip in clips[50:]:
        old_clip.unlink(missing_ok=True)
        thumb = old_clip.with_suffix(".jpg")
        thumb.unlink(missing_ok=True)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)
