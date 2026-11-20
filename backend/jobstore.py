import json
import sqlite3
import threading
import time
import uuid

from config import DB_PATH

_lock = threading.Lock()

# Job lifecycle:
#   pending -> fetching_info -> downloading -> merging -> ready
#                                                        -> failed
#                                                        -> cancelled
#   A job can also become expired once its ready file passes its retention window.
STATUSES = {
    "pending",
    "fetching_info",
    "downloading",
    "merging",
    "ready",
    "failed",
    "cancelled",
    "expired",
}


def _connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    quality INTEGER,
                    status TEXT NOT NULL,
                    progress REAL,
                    speed TEXT,
                    eta TEXT,
                    error TEXT,
                    title TEXT,
                    thumbnail TEXT,
                    duration REAL,
                    author TEXT,
                    filename TEXT,
                    file_path TEXT,
                    file_size INTEGER,
                    request_dir TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    ready_at REAL,
                    expires_at REAL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    worker_pid INTEGER
                )
                """
            )
            conn.commit()
        finally:
            conn.close()


def create_job(url: str, quality: int) -> dict:
    job_id = uuid.uuid4().hex
    now = time.time()
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO jobs (id, url, quality, status, progress, created_at, updated_at, cancel_requested)
                VALUES (?, ?, ?, 'pending', 0, ?, ?, 0)
                """,
                (job_id, url, quality, now, now),
            )
            conn.commit()
        finally:
            conn.close()
    return get_job(job_id)


def get_job(job_id: str):
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def update_job(job_id: str, **fields):
    if not fields:
        return
    fields["updated_at"] = time.time()
    columns = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [job_id]
    with _lock:
        conn = _connect()
        try:
            conn.execute(f"UPDATE jobs SET {columns} WHERE id = ?", values)
            conn.commit()
        finally:
            conn.close()


def request_cancel(job_id: str):
    update_job(job_id, cancel_requested=1)


def is_cancel_requested(job_id: str) -> bool:
    job = get_job(job_id)
    return bool(job and job["cancel_requested"])


def list_jobs_by_status(statuses):
    placeholders = ",".join("?" for _ in statuses)
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM jobs WHERE status IN ({placeholders})", list(statuses)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def list_ready_expirable(now: float):
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = 'ready' AND expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def count_active_jobs() -> int:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as c FROM jobs WHERE status IN ('pending','fetching_info','downloading','merging')"
            ).fetchone()
            return row["c"]
        finally:
            conn.close()
