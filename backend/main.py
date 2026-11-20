import logging
import os

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, field_validator

import jobstore
import worker
from cleanup import run_cleanup_once, start_cleanup_thread
from config import (
    ACCESS_TOKEN,
    ALLOWED_ORIGINS,
    AVAILABLE_QUALITIES,
    MAX_QUEUE_SIZE,
)
from services.analyzer import AnalysisError, analyze_video
from services.downloader import cleanup_request_dir
from utils.validators import URLValidationError, validate_url

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("videopocket.api")

app = FastAPI(title="VideoPocket API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Access-Token"],
    expose_headers=["Content-Disposition", "Content-Range", "Accept-Ranges"],
)


@app.on_event("startup")
def on_startup():
    jobstore.init_db()
    worker.recover_interrupted_jobs()
    run_cleanup_once()
    worker.start_workers()
    start_cleanup_thread()


def _check_access(x_access_token: str | None):
    if ACCESS_TOKEN and x_access_token != ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str


class CreateJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    quality: int

    @field_validator("quality")
    @classmethod
    def quality_must_be_supported(cls, v):
        if v not in AVAILABLE_QUALITIES:
            raise ValueError("unsupported_quality")
        return v


def error_response(status_code: int, error: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"success": False, "error": error})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/analyze")
def analyze(payload: AnalyzeRequest, x_access_token: str | None = Header(default=None)):
    _check_access(x_access_token)

    try:
        clean_url = validate_url(payload.url)
    except URLValidationError as exc:
        return error_response(400, str(exc))

    logger.info("analyze_requested")

    try:
        result = analyze_video(clean_url)
    except AnalysisError as exc:
        status_code = 408 if exc.error_code == "timeout" else 400
        return error_response(status_code, exc.error_code)

    return result


@app.post("/api/jobs")
def create_job(payload: CreateJobRequest, x_access_token: str | None = Header(default=None)):
    _check_access(x_access_token)

    try:
        clean_url = validate_url(payload.url)
    except URLValidationError as exc:
        return error_response(400, str(exc))

    if jobstore.count_active_jobs() >= MAX_QUEUE_SIZE:
        return error_response(429, "queue_full")

    job = jobstore.create_job(clean_url, payload.quality)
    worker.enqueue(job["id"], clean_url, payload.quality)

    logger.info("job_created job_id=%s", job["id"])
    return {"success": True, "job_id": job["id"], "status": job["status"]}


def _job_public_view(job: dict) -> dict:
    return {
        "success": True,
        "job_id": job["id"],
        "status": job["status"],
        "progress": job["progress"],
        "speed": job["speed"],
        "eta": job["eta"],
        "error": job["error"],
        "title": job["title"],
        "filename": job["filename"],
        "file_size": job["file_size"],
        "expires_at": job["expires_at"],
    }


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str, x_access_token: str | None = Header(default=None)):
    _check_access(x_access_token)

    job = jobstore.get_job(job_id)
    if not job:
        return error_response(404, "job_not_found")
    return _job_public_view(job)


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str, x_access_token: str | None = Header(default=None)):
    _check_access(x_access_token)

    job = jobstore.get_job(job_id)
    if not job:
        return error_response(404, "job_not_found")
    if job["status"] in ("ready", "failed", "cancelled", "expired"):
        return _job_public_view(job)

    jobstore.request_cancel(job_id)
    return {"success": True, "job_id": job_id, "status": "cancelling"}


@app.get("/api/jobs/{job_id}/file")
def download_file(job_id: str, request: Request, background_tasks: BackgroundTasks, x_access_token: str | None = Header(default=None)):
    _check_access(x_access_token)

    job = jobstore.get_job(job_id)
    if not job:
        return error_response(404, "job_not_found")
    if job["status"] == "expired":
        return error_response(410, "file_expired")
    if job["status"] != "ready":
        return error_response(400, "file_not_ready")

    file_path = job["file_path"]
    if not file_path or not os.path.isfile(file_path):
        return error_response(410, "file_expired")

    response = FileResponse(
        path=file_path,
        media_type="video/mp4",
        filename=job["filename"],
    )
    response.headers["Accept-Ranges"] = "bytes"
    return response
