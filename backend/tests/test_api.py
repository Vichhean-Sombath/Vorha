import pytest

from app.core.config import settings
from app.routers import sounds
from app.schemas.sound import SoundMetadata
from app.services import audio_service
from app.services.audio_service import AudioExtractionError, ExtractedAudio
from app.services.tiktok_service import TikTokService
from app.services.youtube_service import YouTubeService


async def register(client):
    response = await client.post("/api/v1/auth/register", json={
        "username": "soundfan",
        "email": "sound@example.com",
        "password": "a-strong-password",
    })
    assert response.status_code == 201
    return response.json()["user"]


async def test_register_login_and_current_user(client):
    created = await register(client)
    duplicate = await client.post("/api/v1/auth/register", json={"username": "soundfan", "email": "sound@example.com", "password": "another-strong-password"})
    assert duplicate.status_code == 409
    current = await client.get("/api/v1/auth/me")
    assert current.status_code == 200
    assert current.json()["id"] == created["id"]

    invalid = await client.post("/api/v1/auth/login", json={"email": "sound@example.com", "password": "wrong-password"})
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "INVALID_CREDENTIALS"

    await client.post("/api/v1/auth/logout")
    assert (await client.get("/api/v1/auth/me")).status_code == 401


def test_tiktok_url_validation():
    assert TikTokService.validate_url("https://www.tiktok.com/@user/video/12345")
    with pytest.raises(Exception):
        TikTokService.validate_url("https://not-tiktok.example/@user/video/12345")
    with pytest.raises(Exception):
        TikTokService.validate_url("http://www.tiktok.com/@user/video/12345")


def test_youtube_url_validation():
    watch = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert YouTubeService.validate_url("https://youtu.be/dQw4w9WgXcQ") == watch
    assert YouTubeService.validate_url(f"{watch}&list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf") == watch
    assert YouTubeService.validate_url("https://music.youtube.com/watch?v=dQw4w9WgXcQ") == watch
    assert YouTubeService.validate_url("https://www.youtube.com/shorts/dQw4w9WgXcQ") == watch
    with pytest.raises(Exception):
        YouTubeService.validate_url("https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf")
    with pytest.raises(Exception):
        YouTubeService.validate_url("http://www.youtube.com/watch?v=dQw4w9WgXcQ")
    with pytest.raises(Exception):
        YouTubeService.validate_url("https://not-youtube.example/watch?v=dQw4w9WgXcQ")


def test_platforms_only_claim_their_own_hosts():
    assert TikTokService.matches("https://www.tiktok.com/@user/video/12345")
    assert YouTubeService.matches("https://youtu.be/dQw4w9WgXcQ")
    assert not TikTokService.matches("https://youtu.be/dQw4w9WgXcQ")
    assert not YouTubeService.matches("https://www.tiktok.com/@user/video/12345")
    assert not YouTubeService.matches("https://example.com/watch?v=dQw4w9WgXcQ")
    assert not YouTubeService.matches("http://youtu.be/dQw4w9WgXcQ")


async def test_analyze_playlists_favorites_and_history(client, monkeypatch):
    await register(client)

    async def fake_analyze(source_url: str) -> SoundMetadata:
        return SoundMetadata(
            title="Original sound · Sunday drive",
            creator_name="A creator",
            creator_username="creator",
            source_url=source_url,
            external_id="987654321",
            is_playable=False,
        )

    monkeypatch.setattr(sounds.tiktok_service, "analyze", fake_analyze)
    analyzed = await client.post("/api/v1/sounds/analyze", json={"url": "https://www.tiktok.com/@creator/video/987654321"})
    assert analyzed.status_code == 200
    sound_id = analyzed.json()["id"]
    assert analyzed.json()["playback_url"] is None
    assert analyzed.json()["is_playable"] is False

    playlist = await client.post("/api/v1/playlists", json={"name": "Slow mornings"})
    assert playlist.status_code == 201
    playlist_id = playlist.json()["id"]
    added = await client.post(f"/api/v1/playlists/{playlist_id}/sounds", json={"sound_id": sound_id})
    assert added.status_code == 201
    assert added.json()["items"][0]["sound"]["id"] == sound_id

    assert (await client.post(f"/api/v1/favorites/{sound_id}")).status_code == 204
    favorites = await client.get("/api/v1/favorites")
    assert [item["id"] for item in favorites.json()] == [sound_id]

    history = await client.post("/api/v1/history", json={"sound_id": sound_id, "progress_seconds": 13})
    assert history.status_code == 200
    assert history.json()["progress_seconds"] == 13
    updated_history = await client.patch(f"/api/v1/history/{sound_id}", json={"progress_seconds": 25, "completed": True})
    assert updated_history.json()["completed"] is True

    library = await client.get("/api/v1/sounds?q=Sunday")
    assert library.status_code == 200
    assert library.json()["total"] == 1

    assert (await client.delete(f"/api/v1/favorites/{sound_id}")).status_code == 204
    assert (await client.delete(f"/api/v1/playlists/{playlist_id}/sounds/{sound_id}")).status_code == 204
    assert (await client.delete(f"/api/v1/playlists/{playlist_id}")).status_code == 204
    assert (await client.delete("/api/v1/history")).status_code == 204


async def test_analysis_rejects_unsupported_urls_and_library_requires_auth(client):
    invalid = await client.post("/api/v1/sounds/analyze", json={"url": "https://example.com/video/123"})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "UNSUPPORTED_URL"
    assert (await client.get("/api/v1/sounds")).status_code == 401


VIDEO_URL = "https://www.tiktok.com/@creator/video/987654321"
AUDIO_BYTES = b"ID3audio-bytes"


def stub_metadata(monkeypatch):
    async def fake_analyze(source_url: str) -> SoundMetadata:
        return SoundMetadata(
            title="Original sound · Sunday drive",
            creator_name="A creator",
            creator_username="creator",
            source_url=source_url,
            external_id="987654321",
            is_playable=False,
        )

    monkeypatch.setattr(sounds.tiktok_service, "analyze", fake_analyze)


def stub_youtube_metadata(monkeypatch):
    async def fake_analyze(source_url: str) -> SoundMetadata:
        return SoundMetadata(
            title="Never Gonna Give You Up",
            creator_name="Rick Astley",
            creator_username="rickastley",
            source_url=source_url,
            external_id="dQw4w9WgXcQ",
            is_playable=False,
        )

    monkeypatch.setattr(sounds.youtube_service, "analyze", fake_analyze)


def stub_extraction(monkeypatch, tmp_path, duration=42):
    monkeypatch.setattr(settings, "audio_extraction_enabled", True)
    target = tmp_path / "audio-cache" / f"987654321.{audio_service.AUDIO_EXTENSION}"

    async def fake_ensure(source_url: str, key: str | None, platform: str = "tiktok") -> ExtractedAudio:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(AUDIO_BYTES)
        return ExtractedAudio(path=target, duration_seconds=duration)

    monkeypatch.setattr(sounds.audio_service, "ensure_audio", fake_ensure)
    return target


def test_platform_cache_keys_do_not_collide():
    assert audio_service.platform_key("tiktok", "7106594312292453675") == "7106594312292453675"
    assert audio_service.platform_key(None, "7106594312292453675") == "7106594312292453675"
    assert audio_service.platform_key("youtube", "dQw4w9WgXcQ") == "youtube-dQw4w9WgXcQ"


def test_audio_cache_key_rejects_unsafe_values():
    assert audio_service.normalize_key("7106594312292453675") == "7106594312292453675"
    assert audio_service.normalize_key("../../etc/passwd") is None
    assert audio_service.normalize_key("a/b") is None
    assert audio_service.normalize_key("12") is None
    assert audio_service.normalize_key(None) is None


def test_download_errors_map_to_stable_codes():
    cases = {
        "Private video. Sign in if you have access": ("VIDEO_NOT_FOUND", 404),
        "This video is unavailable": ("VIDEO_NOT_FOUND", 404),
        "Sign in to confirm you are not a bot": ("VIDEO_RESTRICTED", 422),
        "age-restricted": ("VIDEO_RESTRICTED", 422),
        "HTTP Error 429: Too Many Requests": ("RATE_LIMITED", 429),
        "Unsupported URL: https://example.com/x": ("UNSUPPORTED_URL", 422),
        "The uploader has not made this video available in your country": ("VIDEO_RESTRICTED", 422),
        "something completely unexpected": ("AUDIO_EXTRACTION_FAILED", 502),
    }
    for message, (code, status_code) in cases.items():
        error = audio_service._map_download_error(Exception(message))
        assert (error.code, error.status_code) == (code, status_code), message


async def test_disabled_extraction_leaves_sound_unplayable(client, monkeypatch):
    await register(client)
    stub_metadata(monkeypatch)
    analyzed = await client.post("/api/v1/sounds/analyze", json={"url": VIDEO_URL})
    assert analyzed.status_code == 200
    assert analyzed.json()["is_playable"] is False

    retry = await client.post(f"/api/v1/sounds/{analyzed.json()['id']}/audio")
    assert retry.status_code == 503
    assert retry.json()["error"]["code"] == "AUDIO_EXTRACTION_DISABLED"


async def test_analyze_prepares_and_streams_audio(client, monkeypatch, tmp_path):
    await register(client)
    stub_metadata(monkeypatch)
    stub_extraction(monkeypatch, tmp_path)

    analyzed = await client.post("/api/v1/sounds/analyze", json={"url": VIDEO_URL})
    assert analyzed.status_code == 200
    body = analyzed.json()
    sound_id = body["id"]
    assert body["is_playable"] is True
    assert body["playback_url"].startswith(f"/sounds/{sound_id}/stream?t=")
    assert body["duration_seconds"] == 42

    stream = await client.get(f"/api/v1{body['playback_url']}")
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("audio/mpeg")
    assert stream.headers["accept-ranges"] == "bytes"
    assert stream.content == AUDIO_BYTES

    partial = await client.get(f"/api/v1{body['playback_url']}", headers={"Range": "bytes=0-2"})
    assert partial.status_code == 206
    assert partial.content == b"ID3"


async def test_stream_accepts_signed_token_for_guests_and_rejects_bad_tokens(client, monkeypatch, tmp_path):
    stub_metadata(monkeypatch)
    stub_extraction(monkeypatch, tmp_path)

    analyzed = await client.post("/api/v1/sounds/analyze", json={"url": VIDEO_URL})
    playback_url = analyzed.json()["playback_url"]
    sound_id = analyzed.json()["id"]

    await client.post("/api/v1/auth/logout")

    signed_out = await client.get(f"/api/v1{playback_url}")
    assert signed_out.status_code == 200
    assert signed_out.content == AUDIO_BYTES

    assert (await client.get(f"/api/v1/sounds/{sound_id}/stream")).status_code == 401
    tampered = await client.get(f"/api/v1/sounds/{sound_id}/stream", params={"t": "0" * 32})
    assert tampered.status_code == 401
    assert tampered.json()["error"]["code"] == "PLAYBACK_FORBIDDEN"


async def test_prepare_audio_enables_playback_after_retry(client, monkeypatch, tmp_path):
    await register(client)
    stub_metadata(monkeypatch)
    sound_id = (await client.post("/api/v1/sounds/analyze", json={"url": VIDEO_URL})).json()["id"]

    stub_extraction(monkeypatch, tmp_path)
    prepared = await client.post(f"/api/v1/sounds/{sound_id}/audio")
    assert prepared.status_code == 200
    assert prepared.json()["is_playable"] is True
    assert prepared.json()["playback_url"].startswith(f"/sounds/{sound_id}/stream?t=")
    assert (await client.get(f"/api/v1/sounds/{sound_id}/stream")).content == AUDIO_BYTES


async def test_reanalyze_keeps_known_duration(client, monkeypatch, tmp_path):
    await register(client)
    stub_metadata(monkeypatch)
    stub_extraction(monkeypatch, tmp_path, duration=61)

    first = await client.post("/api/v1/sounds/analyze", json={"url": VIDEO_URL})
    assert first.json()["duration_seconds"] == 61

    # A warm cache hit carries no duration, so the stored value must survive.
    stub_extraction(monkeypatch, tmp_path, duration=None)
    second = await client.post("/api/v1/sounds/analyze", json={"url": VIDEO_URL})
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["duration_seconds"] == 61
    assert second.json()["is_playable"] is True

    # A fresh extraction probes the real file, so it outranks the stored value.
    stub_extraction(monkeypatch, tmp_path, duration=148)
    third = await client.post("/api/v1/sounds/analyze", json={"url": VIDEO_URL})
    assert third.json()["duration_seconds"] == 148


async def test_failed_extraction_keeps_metadata_and_reports_reason(client, monkeypatch):
    await register(client)
    stub_metadata(monkeypatch)
    monkeypatch.setattr(settings, "audio_extraction_enabled", True)

    async def failing(source_url: str, key: str | None, platform: str = "tiktok") -> ExtractedAudio:
        raise AudioExtractionError("VIDEO_RESTRICTED", "TikTok is blocking automated access to this video.", 422)

    monkeypatch.setattr(sounds.audio_service, "ensure_audio", failing)

    analyzed = await client.post("/api/v1/sounds/analyze", json={"url": VIDEO_URL})
    assert analyzed.status_code == 200
    assert analyzed.json()["is_playable"] is False
    assert analyzed.json()["playback_url"] is None
    assert analyzed.json()["title"] == "Original sound · Sunday drive"

    retry = await client.post(f"/api/v1/sounds/{analyzed.json()['id']}/audio")
    assert retry.status_code == 422
    assert retry.json()["error"]["code"] == "VIDEO_RESTRICTED"


async def test_analyze_youtube_short_link_streams_namespaced_audio(client, monkeypatch, tmp_path):
    await register(client)
    stub_youtube_metadata(monkeypatch)
    monkeypatch.setattr(settings, "audio_extraction_enabled", True)
    requests: list[tuple[str, str, str]] = []

    async def fake_ensure(source_url: str, key: str | None, platform: str = "tiktok") -> ExtractedAudio:
        requests.append((source_url, key or "", platform))
        target = tmp_path / "audio-cache" / f"{key}.{audio_service.AUDIO_EXTENSION}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(AUDIO_BYTES)
        return ExtractedAudio(path=target, duration_seconds=212)

    monkeypatch.setattr(sounds.audio_service, "ensure_audio", fake_ensure)

    analyzed = await client.post("/api/v1/sounds/analyze", json={"url": "https://youtu.be/dQw4w9WgXcQ"})
    assert analyzed.status_code == 200
    body = analyzed.json()
    assert body["source_platform"] == "youtube"
    assert body["source_url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert body["title"] == "Never Gonna Give You Up"
    assert body["is_playable"] is True
    assert body["duration_seconds"] == 212
    assert requests == [("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube-dQw4w9WgXcQ", "youtube")]

    stream = await client.get(f"/api/v1{body['playback_url']}")
    assert stream.status_code == 200
    assert stream.content == AUDIO_BYTES

    # The same video analyzed again reuses the stored sound and the cached file.
    assert audio_service.has_cached_audio("youtube-dQw4w9WgXcQ")
    again = await client.post("/api/v1/sounds/analyze", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
    assert again.json()["id"] == body["id"]
    assert again.json()["is_playable"] is True
    assert again.json()["duration_seconds"] == 212
