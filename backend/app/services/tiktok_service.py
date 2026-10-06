import asyncio
import logging
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import HTTPException
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.schemas.sound import SoundMetadata

logger = logging.getLogger(__name__)
ALLOWED_HOSTS = {"tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}
SHORT_LINK_HOSTS = {"vm.tiktok.com", "vt.tiktok.com"}
VIDEO_ID = re.compile(r"/video/(\d+)")
OEMBED_URL = "https://www.tiktok.com/oembed"
RETRYABLE_STATUSES = {500, 502, 503, 504}


class _MusicLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_music_link = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        self.in_music_link = tag == "a" and "/music/" in (values.get("href") or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self.in_music_link = False

    def handle_data(self, data: str) -> None:
        if self.in_music_link:
            self.parts.append(data)


class TikTokService:
    """Reads public video metadata through TikTok's documented oEmbed API only."""

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
    def validate_url(source_url: str) -> str:
        parsed = urlparse(source_url)
        try:
            port = parsed.port
        except ValueError:
            port = -1
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password:
            raise HTTPException(status_code=422, detail={"code": "UNSUPPORTED_URL", "message": "Enter a public TikTok video URL."})
        if port not in (None, 443):
            raise HTTPException(status_code=422, detail={"code": "UNSUPPORTED_URL", "message": "Enter a public TikTok video URL."})
        return source_url

    async def analyze(self, source_url: str) -> SoundMetadata:
        source_url = self.validate_url(source_url)
        if urlparse(source_url).hostname in SHORT_LINK_HOSTS:
            source_url = await self._resolve_short_link(source_url)
        path_match = VIDEO_ID.search(urlparse(source_url).path)
        external_id = path_match.group(1) if path_match else None
        cache_key = f"sound:tiktok:{external_id}" if external_id else None
        if cache_key and self.cache and not self.cache_disabled:
            try:
                cached = await self.cache.get(cache_key)
                if cached:
                    return SoundMetadata.model_validate_json(cached)
            except (RedisError, ValueError):
                logger.info("Redis unavailable; continuing without metadata cache")
                self.cache_disabled = True
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=False, headers={"User-Agent": "Vorha/1.0 (public metadata via TikTok oEmbed)"}) as client:
                for attempt in range(3):
                    response = await client.get(OEMBED_URL, params={"url": source_url})
                    if response.status_code not in RETRYABLE_STATUSES or attempt == 2:
                        break
                    retry_after = response.headers.get("retry-after", "")
                    try:
                        delay = min(max(float(retry_after), 0.0), 5.0)
                    except ValueError:
                        delay = 0.75 * (2 ** attempt)
                    await asyncio.sleep(delay)
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail={"code": "VIDEO_NOT_FOUND", "message": "This TikTok video is unavailable or could not be found."})
            if response.status_code in (400, 403):
                raise HTTPException(status_code=404, detail={"code": "VIDEO_NOT_FOUND", "message": "This video may be private, removed, or unavailable for public embedding."})
            if response.status_code == 429:
                raise HTTPException(status_code=429, detail={"code": "RATE_LIMITED", "message": "TikTok is temporarily limiting metadata requests. Try again shortly."}, headers={"Retry-After": response.headers.get("retry-after", "5")})
            if response.status_code in RETRYABLE_STATUSES:
                raise HTTPException(status_code=503, detail={"code": "TIKTOK_TEMPORARILY_UNAVAILABLE", "message": "TikTok’s metadata service is temporarily overloaded. Try again in a few seconds."}, headers={"Retry-After": "5"})
            response.raise_for_status()
            data = response.json()
            if data.get("type") != "video":
                raise HTTPException(status_code=422, detail={"code": "UNSUPPORTED_URL", "message": "This URL does not point to a TikTok video."})
            embed = _MusicLinkParser()
            embed.feed(data.get("html", ""))
            music_title = " ".join("".join(embed.parts).split()).strip("♬ ") or None
            author_url = data.get("author_url") or ""
            author_match = re.search(r"/@([^/?]+)", author_url)
            thumbnail = data.get("thumbnail_url")
            # Only retain safe HTTPS thumbnail URLs returned by TikTok.
            if thumbnail and urlparse(thumbnail).scheme != "https":
                thumbnail = None
            metadata = SoundMetadata(
                title=(music_title or data.get("title") or "TikTok sound")[:255],
                creator_name=(data.get("author_name") or "")[:255] or None,
                creator_username=author_match.group(1)[:255] if author_match else None,
                thumbnail_url=thumbnail,
                playback_url=None,
                duration_seconds=None,
                source_url=source_url,
                external_id=external_id or self._id_from_embed(data.get("html", "")),
                is_playable=False,
            )
            if cache_key and self.cache and not self.cache_disabled:
                try:
                    await self.cache.set(cache_key, metadata.model_dump_json(), ex=43200)
                except RedisError:
                    logger.info("Could not cache TikTok metadata; continuing without Redis")
                    self.cache_disabled = True
            return metadata
        except HTTPException:
            raise
        except httpx.TimeoutException:
            logger.info("TikTok oEmbed timed out")
            raise HTTPException(status_code=503, detail={"code": "EXTERNAL_SERVICE_ERROR", "message": "Video metadata is taking too long to load. Try again shortly."}) from None
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            logger.exception("TikTok oEmbed request failed")
            raise HTTPException(status_code=503, detail={"code": "EXTERNAL_SERVICE_ERROR", "message": "Video metadata is temporarily unavailable."}) from None

    async def _resolve_short_link(self, source_url: str) -> str:
        """Expand TikTok's short share links while rejecting redirects off TikTok."""
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=False, headers={"User-Agent": "Vorha/1.0 (public metadata via TikTok oEmbed)"}) as client:
                current = source_url
                for _ in range(5):
                    async with client.stream("GET", current) as response:
                        if response.status_code not in {301, 302, 303, 307, 308}:
                            return current
                        destination = response.headers.get("location")
                    if not destination:
                        return current
                    current = urljoin(current, destination)
                    current = self.validate_url(current)
                return current
        except HTTPException:
            raise
        except httpx.HTTPError:
            # The oEmbed endpoint may still accept the original public TikTok URL.
            logger.info("Could not expand TikTok short link; trying it directly with oEmbed")
            return source_url

    @staticmethod
    def _id_from_embed(embed_html: str) -> str | None:
        match = re.search(r'data-video-id=["\'](\d+)', embed_html)
        return match.group(1) if match else None
