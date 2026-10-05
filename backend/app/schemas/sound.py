from datetime import datetime

from pydantic import Field, HttpUrl, model_serializer

from app.core.security import stream_signature
from app.schemas.common import ORMModel


class AnalyzeRequest(ORMModel):
    url: HttpUrl


class SoundRead(ORMModel):
    id: int
    source_platform: str
    source_url: str
    external_id: str | None
    title: str | None
    creator_name: str | None
    creator_username: str | None
    thumbnail_url: str | None
    playback_url: str | None
    duration_seconds: int | None
    is_playable: bool
    created_at: datetime

    @model_serializer(mode="wrap")
    def sign_playback_url(self, handler) -> dict:
        """Hand out a signed playback URL without persisting the signature."""
        data = handler(self)
        if data.get("playback_url"):
            data["playback_url"] = f"{data['playback_url']}?t={stream_signature(self.id, self.external_id)}"
        return data


class SoundPage(ORMModel):
    items: list[SoundRead]
    page: int
    limit: int
    total: int


class SoundMetadata(ORMModel):
    title: str | None = None
    creator_name: str | None = None
    creator_username: str | None = None
    thumbnail_url: str | None = None
    playback_url: str | None = None
    duration_seconds: int | None = None
    source_url: str
    external_id: str | None = None
    is_playable: bool = False
