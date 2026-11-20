import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

import yt_dlp

from config import ANALYZE_TIMEOUT, AVAILABLE_QUALITIES, DEFAULT_QUALITY, MAX_VIDEO_DURATION

logger = logging.getLogger("videopocket.analyzer")


class AnalysisError(Exception):
    def __init__(self, error_code: str):
        self.error_code = error_code
        super().__init__(error_code)


def _build_opts() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": ANALYZE_TIMEOUT,
        "extractor_args": {"youtube": {"player_client": ["tv", "android", "web"]}},
    }


def _pick_thumbnail(info: dict):
    thumbnail = info.get("thumbnail")
    if thumbnail:
        return thumbnail
    thumbnails = info.get("thumbnails") or []
    if thumbnails:
        best = max(thumbnails, key=lambda t: (t.get("width") or 0) * (t.get("height") or 0))
        return best.get("url")
    return None


def _pick_author(info: dict):
    return info.get("uploader") or info.get("channel") or info.get("uploader_id") or None


def _real_available_heights(info: dict) -> set:
    """Returns the set of video heights actually present in yt-dlp's format list."""
    heights = set()
    for fmt in info.get("formats") or []:
        height = fmt.get("height")
        vcodec = fmt.get("vcodec")
        if height and vcodec and vcodec != "none":
            heights.add(int(height))
    return heights


def _available_qualities(info: dict) -> list:
    """Only report a quality as available if a real format at or above it exists."""
    real_heights = _real_available_heights(info)
    if not real_heights:
        return []
    max_height = max(real_heights)
    return [q for q in AVAILABLE_QUALITIES if q <= max_height or q == min(AVAILABLE_QUALITIES)]


def _default_quality(available: list) -> int:
    if DEFAULT_QUALITY in available:
        return DEFAULT_QUALITY
    lower_or_equal = [q for q in available if q <= DEFAULT_QUALITY]
    if lower_or_equal:
        return max(lower_or_equal)
    return min(available) if available else DEFAULT_QUALITY


def _estimate_size_for_quality(info: dict, quality: int):
    """Best-effort approximate combined size (bytes) for a given target height, or None."""
    best_video = None
    best_audio = None
    for fmt in info.get("formats") or []:
        height = fmt.get("height")
        vcodec = fmt.get("vcodec")
        acodec = fmt.get("acodec")
        size = fmt.get("filesize") or fmt.get("filesize_approx")
        if not size:
            continue
        if vcodec and vcodec != "none" and height and height <= quality:
            if best_video is None or height > best_video[0]:
                best_video = (height, size)
        if acodec and acodec != "none" and (not vcodec or vcodec == "none"):
            if best_audio is None or size > best_audio:
                best_audio = size

    total = 0
    found = False
    if best_video:
        total += best_video[1]
        found = True
    if best_audio:
        total += best_audio
        found = True
    return total if found else None


def sanitize_info(info: dict) -> dict:
    available = _available_qualities(info)
    qualities = []
    for q in available:
        size = _estimate_size_for_quality(info, q)
        qualities.append({"height": q, "approx_size_bytes": size})

    return {
        "success": True,
        "video_id": info.get("id"),
        "title": info.get("title"),
        "author": _pick_author(info),
        "thumbnail": _pick_thumbnail(info),
        "duration": info.get("duration"),
        "webpage_url": info.get("webpage_url") or info.get("original_url"),
        "qualities": qualities,
        "default_quality": _default_quality(available),
    }


def _extract(url: str, opts: dict):
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def analyze_video(url: str) -> dict:
    opts = _build_opts()

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_extract, url, opts)
            info = future.result(timeout=ANALYZE_TIMEOUT)
    except FutureTimeoutError:
        logger.warning("analyze_failed error_type=timeout")
        raise AnalysisError("timeout")
    except yt_dlp.utils.DownloadError as exc:
        message = str(exc).lower()
        logger.warning("analyze_failed error_type=download_error")
        if "confirm you" in message and ("bot" in message or "not a bot" in message):
            raise AnalysisError("bot_check")
        if "private" in message or "login" in message or "log in" in message or "sign in" in message:
            raise AnalysisError("private_video")
        if "live" in message and "not currently live" not in message:
            raise AnalysisError("live_stream")
        if "not available" in message or "unavailable" in message or "removed" in message:
            raise AnalysisError("video_unavailable")
        raise AnalysisError("analysis_failed")
    except Exception:
        logger.warning("analyze_failed error_type=unexpected")
        raise AnalysisError("analysis_failed")

    if not info:
        raise AnalysisError("analysis_failed")

    if info.get("is_live"):
        raise AnalysisError("live_stream")

    duration = info.get("duration")
    if duration is not None and duration > MAX_VIDEO_DURATION:
        logger.warning("analyze_failed error_type=video_too_long")
        raise AnalysisError("video_too_long")

    logger.info("analyze_success")
    return sanitize_info(info)
