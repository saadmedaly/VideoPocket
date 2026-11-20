import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
DB_PATH = os.path.join(BASE_DIR, "jobs.sqlite3")

DEFAULT_ALLOWED_ORIGINS = "http://127.0.0.1:5500,http://localhost:5500"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS).split(",")
    if origin.strip()
]

PORT = int(os.environ.get("PORT", "8200"))

# Optional simple access token for internet-exposed deployments (not used locally).
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN", "").strip() or None

MAX_URL_LENGTH = 2048
ANALYZE_TIMEOUT = 25  # seconds

# Long-video support: no artificial 30-minute cap. Bounded by real resources instead.
MAX_VIDEO_DURATION = int(os.environ.get("MAX_VIDEO_DURATION", str(3 * 3600)))  # 3 hours
MAX_DOWNLOAD_SIZE = int(os.environ.get("MAX_DOWNLOAD_SIZE", str(1536 * 1024 * 1024)))  # 1.5 GB
DOWNLOAD_TIMEOUT = int(os.environ.get("DOWNLOAD_TIMEOUT", str(45 * 60)))  # 45 minutes

MAX_QUEUE_SIZE = int(os.environ.get("MAX_QUEUE_SIZE", "10"))
DOWNLOAD_WORKERS = int(os.environ.get("DOWNLOAD_WORKERS", "1"))

# Minimum free disk space (bytes) required on DOWNLOADS_DIR's volume before starting a job.
MIN_FREE_DISK_SPACE = int(os.environ.get("MIN_FREE_DISK_SPACE", str(1024 * 1024 * 1024)))  # 1 GB

FILE_RETENTION_SECONDS = int(os.environ.get("FILE_RETENTION_SECONDS", "3600"))  # 1 hour
CLEANUP_INTERVAL_SECONDS = int(os.environ.get("CLEANUP_INTERVAL_SECONDS", "300"))  # 5 minutes

ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
}
YOUTU_BE_HOST = "youtu.be"

AVAILABLE_QUALITIES = [360, 480, 720, 1080]
DEFAULT_QUALITY = 720
