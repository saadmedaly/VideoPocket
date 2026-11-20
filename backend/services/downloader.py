import logging
import os
import re
import shutil

import yt_dlp

import jobstore
from config import (
    DOWNLOAD_TIMEOUT,
    DOWNLOADS_DIR,
    MAX_DOWNLOAD_SIZE,
    MAX_VIDEO_DURATION,
    MIN_FREE_DISK_SPACE,
)

logger = logging.getLogger("videopocket.downloader")

TEMP_EXTENSIONS = {".part", ".ytdl", ".part-Frag", ".ff", ".temp"}

_VIDEO_TOO_LONG = "__video_too_long__"
_FILESIZE_REJECTED = "__filesize_exceeds_limit__"
_CANCELLED = "__job_cancelled__"


class DownloadError(Exception):
    def __init__(self, error_code: str):
        self.error_code = error_code
        super().__init__(error_code)


class JobCancelled(Exception):
    pass


def _sanitize_id(video_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", video_id or "")
    return safe or "video"


def _is_temp_file(filename: str) -> bool:
    lower = filename.lower()
    return any(lower.endswith(ext.lower()) or ".part" in lower or ".ytdl" in lower for ext in TEMP_EXTENSIONS)


def _find_output_file(request_dir: str) -> str:
    candidates = []
    for name in os.listdir(request_dir):
        full_path = os.path.join(request_dir, name)
        if not os.path.isfile(full_path):
            continue
        if _is_temp_file(name):
            continue
        candidates.append(full_path)
    if len(candidates) != 1:
        raise DownloadError("download_failed")
    return candidates[0]


def _format_selector(quality: int) -> str:
    return (
        f"bestvideo[ext=mp4][height<={quality}]+bestaudio[ext=m4a]"
        f"/bestvideo[height<={quality}]+bestaudio"
        f"/best[ext=mp4][height<={quality}]"
        f"/best[height<={quality}]"
        f"/best"
    )


def _check_disk_space():
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    usage = shutil.disk_usage(DOWNLOADS_DIR)
    if usage.free < MIN_FREE_DISK_SPACE:
        raise DownloadError("insufficient_disk_space")


def run_download_job(job_id: str, url: str, quality: int):
    """Runs synchronously inside the single download worker thread/process."""
    request_dir = os.path.join(DOWNLOADS_DIR, job_id)
    os.makedirs(request_dir, exist_ok=True)

    real_downloads = os.path.realpath(DOWNLOADS_DIR)
    real_request_dir = os.path.realpath(request_dir)
    if os.path.commonpath([real_downloads, real_request_dir]) != real_downloads:
        shutil.rmtree(request_dir, ignore_errors=True)
        raise DownloadError("download_failed")

    try:
        _check_disk_space()
    except DownloadError:
        shutil.rmtree(request_dir, ignore_errors=True)
        raise

    jobstore.update_job(job_id, status="fetching_info", progress=0)

    ydl_ref = {}

    def pre_download_filter(info_dict, *, incomplete=False):
        if jobstore.is_cancel_requested(job_id):
            return _CANCELLED
        duration = info_dict.get("duration")
        if duration is not None and duration > MAX_VIDEO_DURATION:
            return _VIDEO_TOO_LONG
        filesize = info_dict.get("filesize") or info_dict.get("filesize_approx")
        if filesize is not None and filesize > MAX_DOWNLOAD_SIZE:
            return _FILESIZE_REJECTED
        return None

    def progress_hook(d):
        if jobstore.is_cancel_requested(job_id):
            raise JobCancelled()

        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes") or 0
            progress = (downloaded / total * 100) if total else None
            speed = d.get("speed")
            eta = d.get("eta")
            jobstore.update_job(
                job_id,
                status="downloading",
                progress=progress,
                speed=(f"{speed:.0f}" if speed else None),
                eta=(str(eta) if eta is not None else None),
            )
        elif status == "finished":
            jobstore.update_job(job_id, status="merging", progress=100, speed=None, eta=None)

    def postprocessor_hook(d):
        if jobstore.is_cancel_requested(job_id):
            raise JobCancelled()
        if d.get("status") == "started":
            jobstore.update_job(job_id, status="merging")

    output_template = os.path.join(request_dir, "%(id)s.%(ext)s")
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": _format_selector(quality),
        "merge_output_format": "mp4",
        "outtmpl": output_template,
        "socket_timeout": DOWNLOAD_TIMEOUT,
        "paths": {"home": request_dir, "temp": request_dir},
        "restrictfilenames": True,
        "match_filter": pre_download_filter,
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [postprocessor_hook],
        "retries": 2,
        "fragment_retries": 2,
        "extractor_args": {"youtube": {"player_client": ["tv", "android", "web"]}},
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl_ref["ydl"] = ydl
            info = ydl.extract_info(url, download=True)
    except JobCancelled:
        shutil.rmtree(request_dir, ignore_errors=True)
        raise DownloadError("cancelled")
    except yt_dlp.utils.DownloadError as exc:
        message = str(exc).lower()
        shutil.rmtree(request_dir, ignore_errors=True)

        if _CANCELLED.lower() in message:
            raise DownloadError("cancelled")
        if _VIDEO_TOO_LONG.lower() in message:
            logger.warning("download_failed error_type=video_too_long")
            raise DownloadError("video_too_long")
        if _FILESIZE_REJECTED.lower() in message:
            logger.warning("download_failed error_type=file_too_large")
            raise DownloadError("file_too_large")

        logger.warning("download_failed error_type=download_error")
        if "confirm you" in message and ("bot" in message or "not a bot" in message):
            raise DownloadError("bot_check")
        if "private" in message or "login" in message or "log in" in message or "sign in" in message:
            raise DownloadError("private_video")
        if "not available" in message or "unavailable" in message or "removed" in message:
            raise DownloadError("video_unavailable")
        raise DownloadError("download_failed")
    except Exception:
        logger.warning("download_failed error_type=unexpected")
        shutil.rmtree(request_dir, ignore_errors=True)
        raise DownloadError("download_failed")

    if jobstore.is_cancel_requested(job_id):
        shutil.rmtree(request_dir, ignore_errors=True)
        raise DownloadError("cancelled")

    if not info:
        shutil.rmtree(request_dir, ignore_errors=True)
        raise DownloadError("download_failed")

    duration = info.get("duration")
    if duration is not None and duration > MAX_VIDEO_DURATION:
        shutil.rmtree(request_dir, ignore_errors=True)
        raise DownloadError("video_too_long")

    try:
        output_path = _find_output_file(request_dir)
    except DownloadError:
        shutil.rmtree(request_dir, ignore_errors=True)
        raise

    file_size = os.path.getsize(output_path)
    if file_size > MAX_DOWNLOAD_SIZE:
        shutil.rmtree(request_dir, ignore_errors=True)
        raise DownloadError("file_too_large")

    if file_size == 0:
        shutil.rmtree(request_dir, ignore_errors=True)
        raise DownloadError("download_failed")

    video_id = _sanitize_id(str(info.get("id") or "video"))
    filename = f"videopocket-{video_id}-{quality}p.mp4"

    logger.info("download_success file_size=%s", file_size)

    return {
        "request_dir": request_dir,
        "file_path": output_path,
        "filename": filename,
        "file_size": file_size,
        "title": info.get("title"),
    }


def cleanup_request_dir(request_dir: str) -> None:
    if request_dir:
        shutil.rmtree(request_dir, ignore_errors=True)
