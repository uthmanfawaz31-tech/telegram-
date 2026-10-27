import os
import uuid
import shutil
import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

# Base upload directory
UPLOAD_DIR = os.path.abspath(os.path.join(os.getcwd(), "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Allowed extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"}
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS

class MediaUploadResponse(BaseModel):
    file_path: str
    file_url: str
    filename: str
    media_type: str # "image" or "video"

@router.post("/upload", response_model=MediaUploadResponse)
async def upload_media(file: UploadFile = File(...)):
    """
    Upload an image or video to be attached to broadcast messages or templates.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected")

    _, ext = os.path.splitext(file.filename.lower())
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed types: images ({', '.join(IMAGE_EXTENSIONS)}) and videos ({', '.join(VIDEO_EXTENSIONS)})"
        )

    # Determine media type
    media_type = "image" if ext in IMAGE_EXTENSIONS else "video"

    # Generate unique, collision-proof filename
    unique_name = f"{uuid.uuid4().hex[:12]}_{os.path.basename(file.filename)}"
    destination_path = os.path.join(UPLOAD_DIR, unique_name)

    try:
        with open(destination_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    public_url = os.getenv("RENDER_EXTERNAL_URL", "https://telepro-back.onrender.com").rstrip("/")
    file_url = f"{public_url}/api/v1/media/{unique_name}"

    logger.info(f"Media uploaded successfully: {destination_path} ({media_type})")

    return MediaUploadResponse(
        file_path=destination_path,
        file_url=file_url,
        filename=unique_name,
        media_type=media_type
    )

@router.get("/{filename}")
async def serve_media(filename: str):
    """
    Serve uploaded image or video for live preview.
    """
    safe_name = os.path.basename(filename)
    file_path = os.path.join(UPLOAD_DIR, safe_name)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Media file not found")

    _, ext = os.path.splitext(safe_name.lower())
    media_type = "image/jpeg"
    if ext in {".png"}:
        media_type = "image/png"
    elif ext in {".webp"}:
        media_type = "image/webp"
    elif ext in {".gif"}:
        media_type = "image/gif"
    elif ext in {".mp4"}:
        media_type = "video/mp4"
    elif ext in {".mov"}:
        media_type = "video/quicktime"
    elif ext in {".webm"}:
        media_type = "video/webm"

    return FileResponse(file_path, media_type=media_type)
