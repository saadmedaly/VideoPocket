import logging
import os
import threading
import time

import jobstore
from config import CLEANUP_INTERVAL_SECONDS, DOWNLOADS_DIR
from services.downloader import cleanup_request_dir

logger = logging.getLogger("videopocket.cleanup")


def _expire_ready_jobs():
    now = time.time()
    for job in jobstore.list_ready_expirable(now):
        cleanup_request_dir(job.get("request_dir"))
        jobstore.update_job(job["id"], status="expired", file_path=None)
        logger.info("expired job_id=%s", job["id"])


def _sweep_orphan_dirs():
    """Removes download subfolders with no matching active/ready job row (crash leftovers)."""
    if not os.path.isdir(DOWNLOADS_DIR):
        return
    active_or_ready = jobstore.list_jobs_by_status(
        ["pending", "fetching_info", "downloading", "merging", "ready"]
    )
    known_ids = {job["id"] for job in active_or_ready}
    for name in os.listdir(DOWNLOADS_DIR):
        full_path = os.path.join(DOWNLOADS_DIR, name)
        if os.path.isdir(full_path) and name not in known_ids:
            cleanup_request_dir(full_path)
            logger.info("swept orphan download dir=%s", name)


def run_cleanup_once():
    _expire_ready_jobs()
    _sweep_orphan_dirs()


def _cleanup_loop():
    while True:
        try:
            run_cleanup_once()
        except Exception:
            logger.exception("cleanup_loop_error")
        time.sleep(CLEANUP_INTERVAL_SECONDS)


def start_cleanup_thread():
    t = threading.Thread(target=_cleanup_loop, name="cleanup-thread", daemon=True)
    t.start()
