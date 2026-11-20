import ipaddress
import re
from urllib.parse import parse_qs, urlparse

from config import ALLOWED_HOSTS, MAX_URL_LENGTH, YOUTU_BE_HOST

ALLOWED_SCHEMES = {"http", "https"}
LOCAL_HOSTNAMES = {"localhost"}

YOUTUBE_SHORTS_PATH_RE = re.compile(r"^/shorts/([A-Za-z0-9_-]{6,})$")
YOUTUBE_WATCH_PATH_RE = re.compile(r"^/watch/?$")
YOUTU_BE_PATH_RE = re.compile(r"^/([A-Za-z0-9_-]{6,})$")
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,}$")

# Paths that are never a single downloadable video, even on an allowed host.
REJECTED_PATH_PREFIXES = (
    "/playlist",
    "/live",
    "/channel",
    "/c/",
    "/@",
    "/results",
    "/user",
    "/feed",
    "/hashtag",
)


class URLValidationError(Exception):
    pass


def _is_private_host(hostname: str) -> bool:
    if hostname in LOCAL_HOSTNAMES:
        return True
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _host_matches_allowed(hostname: str) -> bool:
    hostname = hostname.lower()
    return any(hostname == allowed or hostname.endswith(f".{allowed}") for allowed in ALLOWED_HOSTS)


def _is_rejected_path(path: str) -> bool:
    path_lower = path.lower()
    return any(path_lower.startswith(prefix) for prefix in REJECTED_PATH_PREFIXES)


def _is_youtu_be(hostname: str) -> bool:
    return hostname == YOUTU_BE_HOST or hostname.endswith(f".{YOUTU_BE_HOST}")


def _classify_path(hostname: str, path: str, query: str) -> None:
    """Raises URLValidationError if the path/host does not point at exactly one video."""
    if _is_youtu_be(hostname):
        if _is_rejected_path(path):
            raise URLValidationError("unsupported_link")
        match = YOUTU_BE_PATH_RE.match(path)
        if not match or not VIDEO_ID_RE.match(match.group(1)):
            raise URLValidationError("unsupported_link")
        return

    if YOUTUBE_SHORTS_PATH_RE.match(path):
        return

    if _is_rejected_path(path):
        raise URLValidationError("unsupported_link")

    if YOUTUBE_WATCH_PATH_RE.match(path):
        params = parse_qs(query)
        video_ids = params.get("v")
        if not video_ids or not VIDEO_ID_RE.match(video_ids[0]):
            raise URLValidationError("unsupported_link")
        # A playlist id alongside v= still points at one video when opened
        # directly; yt-dlp's noplaylist option keeps us to that one video.
        return

    raise URLValidationError("unsupported_link")


def validate_url(url: str) -> str:
    """Validates and normalizes a supported YouTube video URL. Returns the cleaned URL string."""
    if not url or not url.strip():
        raise URLValidationError("invalid_url")

    url = url.strip()

    if len(url) > MAX_URL_LENGTH:
        raise URLValidationError("invalid_url")

    try:
        parsed = urlparse(url)
    except ValueError:
        raise URLValidationError("invalid_url")

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise URLValidationError("invalid_url")

    if not parsed.hostname:
        raise URLValidationError("invalid_url")

    if parsed.username or parsed.password:
        raise URLValidationError("invalid_url")

    hostname = parsed.hostname.lower()

    if _is_private_host(hostname):
        raise URLValidationError("invalid_url")

    if not _is_youtu_be(hostname) and not _host_matches_allowed(hostname):
        raise URLValidationError("unsupported_link")

    _classify_path(hostname, parsed.path, parsed.query)

    return url
