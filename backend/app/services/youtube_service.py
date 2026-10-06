import asyncio
import logging
import re
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import HTTPException
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.schemas.sound import SoundMetadata

logger = logging.getLogger(__name__)
ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
# Paths whose second segment is the video id: /shorts/, /embed/, /live/, /v/.
ID_PATHS = {"shorts", "embed", "live", "v"}
OEMBED_URL = "https://www.youtube.com/oembed"
RETRYABLE_STATUSES = {500, 502, 503, 504}


class YouTubeService:
    """Reads public video metadata through YouTube's documented oEmbed API only."""

    def __init__(self) -> None:
        self.cache = Redis.from_url(settings.redis_url, socket_connect_timeout=0.35, socket_timeout=0.5, decode_responses=True) if settings.redis_url else None
        self.cache_disabled = False

    async def close(self) -> None:
        if self.cache:
            await self.cache.aclose()

    @staticmethod
    def matches(source_url: str) -> bool:
        """Cheap host check used to route a pasted link to the right platform service."""
        try:
            parsed = urlparse(source_url)
            return parsed.scheme == "https" and parsed.hostname in ALLOWED_HOSTS and parsed.port in (None, 443)
        except ValueError:
            return False

    @staticmethod
    def video_id(source_url: str) -> str | None:
        parsed = urlparse(source_url)
        segments = [part for part in parsed.path.split("/") if part]
        candidate = None
        if parsed.hostname == "youtu.be":
            candidate = segments[0] if segments else None
        elif segments and segments[0] == "watch":
            candidate = (parse_qs(parsed.query).get("v") or [None])[0]
        elif len(segments) == 2 and segments[0] in ID_PATHS:
            candidate = segments[1]
        return candidate if candidate and VIDEO_ID.match(candidate) else None

    @classmethod
    def canonical_url(cls, external_id: str) -> str:
        return f"https://www.youtube.com/watch?v={external_id}"

    @classmethod
    def validate_url(cls, source_url: str) -> str:
        parsed = urlparse(source_url)
        try:
            port = parsed.port
        except ValueError:
            port = -1
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password or port not in (None, 443):
            raise HTTPException(status_code=422, detail={"code": "UNSUPPORTED_URL", "message": "Enter a public YouTube video URL."})
        external_id = cls.video_id(source_url)
        if not external_id:
            raise HTTPException(status_code=422, detail={"code": "UNSUPPORTED_URL", "message": "That YouTube link does not point to a single video."})
        return cls.canonical_url(external_id)

    async def analyze(self, source_url: str) -> SoundMetadata:
        source_url = self.validate_url(source_url)
        external_id = self.video_id(source_url)
        cache_key = f"sound:youtube:{external_id}"
        if self.cache and not self.cache_disabled:
            try:
                cached = await self.cache.get(cache_key)
                if cached:
                    return SoundMetadata.model_validate_json(cached)
            except (RedisError, ValueError):
                logger.info("Redis unavailable; continuing without metadata cache")
                self.cache_disabled = True
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=False, headers={"User-Agent": "Vorha/1.0 (public metadata via YouTube oEmbed)"}) as client:
                for attempt in range(3):
                    response = await client.get(OEMBED_URL, params={"url": source_url, "format": "json"})
                    if response.status_code not in RETRYABLE_STATUSES or attempt == 2:
                        break
                    retry_after = response.headers.get("retry-after", "")
                    try:
                        delay = min(max(float(retry_after), 0.0), 5.0)
                    except ValueError:
                        delay = 0.75 * (2 ** attempt)
                    await asyncio.sleep(delay)
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail={"code": "VIDEO_NOT_FOUND", "message": "This YouTube video is unavailable or could not be found."})
            if response.status_code in (400, 401, 403):
                raise HTTPException(status_code=404, detail={"code": "VIDEO_NOT_FOUND", "message": "This video may be private, age-restricted, or unavailable for public embedding."})
            if response.status_code == 429:
                raise HTTPException(status_code=429, detail={"code": "RATE_LIMITED", "message": "YouTube is temporarily limiting metadata requests. Try again shortly."}, headers={"Retry-After": response.headers.get("retry-after", "5")})
            if response.status_code in RETRYABLE_STATUSES:
                raise HTTPException(status_code=503, detail={"code": "YOUTUBE_TEMPORARILY_UNAVAILABLE", "message": "YouTube’s metadata service is temporarily overloaded. Try again in a few seconds."}, headers={"Retry-After": "5"})
            response.raise_for_status()
            data = response.json()
            if data.get("type") != "video":
                raise HTTPException(status_code=422, detail={"code": "UNSUPPORTED_URL", "message": "This URL does not point to a YouTube video."})
            author_url = data.get("author_url") or ""
            author_match = re.search(r"/@([^/?]+)", author_url)
            thumbnail = data.get("thumbnail_url")
            # Only retain safe HTTPS thumbnail URLs returned by YouTube.
            if thumbnail and urlparse(thumbnail).scheme != "https":
                thumbnail = None
            metadata = SoundMetadata(
                title=(data.get("title") or "YouTube video")[:255],
                creator_name=(data.get("author_name") or "")[:255] or None,
                creator_username=author_match.group(1)[:255] if author_match else None,
                thumbnail_url=thumbnail,
                playback_url=None,
                # oEmbed reports no duration; audio extraction probes the real file.
                duration_seconds=None,
                source_url=source_url,
                external_id=external_id,
                is_playable=False,
            )
            if self.cache and not self.cache_disabled:
                try:
                    await self.cache.set(cache_key, metadata.model_dump_json(), ex=43200)
                except RedisError:
                    logger.info("Could not cache YouTube metadata; continuing without Redis")
                    self.cache_disabled = True
            return metadata
        except HTTPException:
            raise
        except httpx.TimeoutException:
            logger.info("YouTube oEmbed timed out")
            raise HTTPException(status_code=503, detail={"code": "EXTERNAL_SERVICE_ERROR", "message": "Video metadata is taking too long to load. Try again shortly."}) from None
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            logger.exception("YouTube oEmbed request failed")
            raise HTTPException(status_code=503, detail={"code": "EXTERNAL_SERVICE_ERROR", "message": "Video metadata is temporarily unavailable."}) from None
