import logging
import queue
import threading
import time

import jobstore
from config import DOWNLOAD_WORKERS, FILE_RETENTION_SECONDS
from services.downloader import DownloadError, run_download_job

logger = logging.getLogger("videopocket.worker")

_job_queue = queue.Queue()
_workers_started = False


def enqueue(job_id: str, url: str, quality: int):
    _job_queue.put((job_id, url, quality))


def _process_job(job_id: str, url: str, quality: int):
    job = jobstore.get_job(job_id)
    if not job:
        return
    if jobstore.is_cancel_requested(job_id):
        jobstore.update_job(job_id, status="cancelled")
        return

    try:
        result = run_download_job(job_id, url, quality)
    except DownloadError as exc:
        if exc.error_code == "cancelled":
            jobstore.update_job(job_id, status="cancelled", progress=None)
        else:
            jobstore.update_job(job_id, status="failed", error=exc.error_code)
        return
    except Exception:
        logger.exception("unexpected_worker_error job_id=%s", job_id)
        jobstore.update_job(job_id, status="failed", error="download_failed")
        return

    now = time.time()
    jobstore.update_job(
        job_id,
        status="ready",
        progress=100,
        title=result.get("title"),
        filename=result["filename"],
        file_path=result["file_path"],
        file_size=result["file_size"],
        request_dir=result["request_dir"],
        ready_at=now,
        expires_at=now + FILE_RETENTION_SECONDS,
    )


def _worker_loop():
    while True:
        job_id, url, quality = _job_queue.get()
        try:
            _process_job(job_id, url, quality)
        except Exception:
            logger.exception("worker_loop_crash job_id=%s", job_id)
        finally:
            _job_queue.task_done()


def start_workers():
    global _workers_started
    if _workers_started:
        return
    _workers_started = True
    for i in range(max(1, DOWNLOAD_WORKERS)):
        t = threading.Thread(target=_worker_loop, name=f"download-worker-{i}", daemon=True)
        t.start()
    logger.info("started %s download worker(s)", DOWNLOAD_WORKERS)


def recover_interrupted_jobs():
    """Called on startup: jobs stuck mid-flight from a previous process are marked failed."""
    stuck = jobstore.list_jobs_by_status(["pending", "fetching_info", "downloading", "merging"])
    for job in stuck:
        jobstore.update_job(job["id"], status="failed", error="interrupted_by_restart")
    if stuck:
        logger.info("marked %s interrupted job(s) as failed after restart", len(stuck))
