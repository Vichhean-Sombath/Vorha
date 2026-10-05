from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

AUDIO_MEDIA_TYPE = "audio/mpeg"
AUDIO_EXTENSION = "mp3"
MAX_CONCURRENT_EXTRACTIONS = 2
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

SAFE_KEY = re.compile(r"^[A-Za-z0-9_-]{4,80}$")

# Ordered so the most specific platform refusal wins; patterns are matched case-insensitively.
_ERROR_RULES: tuple[tuple[str, str, str, int], ...] = (
    (r"private video|only the owner", "VIDEO_NOT_FOUND", "This TikTok video is private.", 404),
    (r"sign in to confirm|login required|account\s+or\s+log\s?in|captcha", "VIDEO_RESTRICTED", "TikTok is blocking automated access to this video. Attach a local file instead.", 422),
    (r"age[\s_-]?restrict", "VIDEO_RESTRICTED", "This video is age-restricted and cannot be fetched automatically.", 422),
    (r"throttl|\b429\b|too many requests|rate[\s_-]?limit", "RATE_LIMITED", "TikTok is limiting automated requests. Try again shortly.", 429),
    (r"unsupported url|no video|is not a valid url", "UNSUPPORTED_URL", "This URL does not point to a downloadable TikTok video.", 422),
    (r"removed|unavailable|not available|does not exist|\b404\b|no such file", "VIDEO_NOT_FOUND", "This TikTok video is unavailable or was removed.", 404),
    (r"ffmpeg|ffprobe", "AUDIO_EXTRACTION_UNAVAILABLE", "Audio conversion failed on the server.", 503),
)

_semaphore = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTIONS)
_locks: dict[str, tuple[asyncio.Lock, int]] = {}


class AudioExtractionError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class ExtractedAudio:
    path: Path
    duration_seconds: int | None


def cache_root() -> Path:
    return Path(settings.audio_cache_dir).expanduser()


def normalize_key(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    return candidate if SAFE_KEY.match(candidate) else None


def audio_path(key: str) -> Path:
    return cache_root() / f"{key}.{AUDIO_EXTENSION}"


def has_cached_audio(key: str | None) -> bool:
    return bool(key) and audio_path(key).is_file() and audio_path(key).stat().st_size > 0


def cached_audio(key: str | None) -> ExtractedAudio | None:
    if not has_cached_audio(key):
        return None
    path = audio_path(key or "")
    return ExtractedAudio(path=path, duration_seconds=None)


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


async def ensure_audio(source_url: str, key: str | None) -> ExtractedAudio:
    """Return the audio-only file for a video, extracting and caching it on first use."""
    cache_key = normalize_key(key)
    if not cache_key:
        raise AudioExtractionError("UNSUPPORTED_URL", "This TikTok link does not identify a single video.", 422)
    existing = cached_audio(cache_key)
    if existing:
        return existing
    if not settings.audio_extraction_enabled:
        raise AudioExtractionError("AUDIO_EXTRACTION_DISABLED", "Audio extraction is turned off on this server.", 503)
    if not ffmpeg_available():
        raise AudioExtractionError("AUDIO_EXTRACTION_UNAVAILABLE", "ffmpeg is not installed on the server, so audio cannot be prepared.", 503)

    lock, held = _locks.get(cache_key, (asyncio.Lock(), 0))
    _locks[cache_key] = (lock, held + 1)
    try:
        async with lock, _semaphore:
            existing = cached_audio(cache_key)
            if existing:
                return existing
            return await asyncio.wait_for(
                asyncio.to_thread(_extract, source_url, cache_key),
                timeout=settings.audio_extract_timeout_seconds,
            )
    except asyncio.TimeoutError:
        logger.info("Audio extraction timed out for %s", cache_key)
        raise AudioExtractionError("AUDIO_EXTRACTION_TIMEOUT", "Preparing this audio took too long. Try again.", 504) from None
    finally:
        lock, held = _locks[cache_key]
        if held <= 1:
            _locks.pop(cache_key, None)
        else:
            _locks[cache_key] = (lock, held - 1)


def remove_cached_audio(key: str | None) -> None:
    cache_key = normalize_key(key)
    if not cache_key:
        return
    try:
        audio_path(cache_key).unlink(missing_ok=True)
    except OSError:
        logger.info("Could not delete cached audio for %s", cache_key)


def _extract(source_url: str, cache_key: str) -> ExtractedAudio:
    try:
        import yt_dlp
        from yt_dlp.utils import DownloadError, ExtractorError
    except ImportError as error:  # pragma: no cover - dependency is declared in requirements.txt
        raise AudioExtractionError("AUDIO_EXTRACTION_UNAVAILABLE", "The audio extractor is not installed on the server.", 503) from error

    root = cache_root()
    root.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix=f"{cache_key}-", dir=root))
    options = {
        "format": "bestaudio/best",
        "outtmpl": str(workdir / f"{cache_key}.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 1,
        "fragment_retries": 1,
        "socket_timeout": 20,
        "overwrites": True,
        "http_headers": {"User-Agent": USER_AGENT, "Referer": "https://www.tiktok.com/"},
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": AUDIO_EXTENSION, "preferredquality": settings.audio_bitrate},
        ],
    }
    try:
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(source_url, download=True)
        except (DownloadError, ExtractorError) as error:
            raise _map_download_error(error) from error
        except Exception as error:  # noqa: BLE001 - yt-dlp raises many extractor-specific types
            logger.info("Audio extraction failed for %s: %s", cache_key, error)
            raise AudioExtractionError("AUDIO_EXTRACTION_FAILED", "Could not fetch audio for this video.", 502) from error

        produced = workdir / f"{cache_key}.{AUDIO_EXTENSION}"
        if not produced.is_file():
            candidates = sorted(workdir.glob(f"{cache_key}.*"))
            produced = candidates[0] if candidates else None
        if produced is None or not produced.is_file():
            raise AudioExtractionError("AUDIO_EXTRACTION_FAILED", "This video has no audio track that could be saved.", 422)

        size = produced.stat().st_size
        if size == 0:
            raise AudioExtractionError("AUDIO_EXTRACTION_FAILED", "This video has no audio track that could be saved.", 422)
        if size > settings.audio_max_bytes:
            raise AudioExtractionError("AUDIO_TOO_LARGE", "This video's audio is longer than the server allows.", 422)

        reported = info.get("duration") if isinstance(info, dict) else None
        destination = audio_path(cache_key)
        # The produced file is the source of truth; extractors sometimes report the
        # clip length rather than the length of the audio they handed us.
        duration_seconds = _probe_duration(produced) or (int(reported) if isinstance(reported, (int, float)) and reported > 0 else None)
        os.replace(produced, destination)
        return ExtractedAudio(path=destination, duration_seconds=duration_seconds)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _probe_duration(path: Path) -> int | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        completed = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        seconds = float(completed.stdout.strip())
    except ValueError:
        return None
    return int(round(seconds)) if seconds > 0 else None


def _map_download_error(error: Exception) -> AudioExtractionError:
    text = str(error).lower()
    for pattern, code, message, status_code in _ERROR_RULES:
        if re.search(pattern, text):
            return AudioExtractionError(code, message, status_code)
    logger.info("Audio extraction rejected: %s", error)
    return AudioExtractionError("AUDIO_EXTRACTION_FAILED", "Could not fetch audio for this video.", 502)
