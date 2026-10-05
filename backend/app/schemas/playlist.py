from datetime import datetime
import base64
import binascii

from pydantic import Field, field_validator

from app.schemas.common import ORMModel
from app.schemas.sound import SoundRead


class PlaylistCreate(ORMModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Playlist name cannot be empty.")
        return name


class PlaylistPatch(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    cover_image: str | None = Field(default=None, max_length=900_000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        name = value.strip()
        if not name:
            raise ValueError("Playlist name cannot be empty.")
        return name

    @field_validator("cover_image")
    @classmethod
    def validate_cover_image(cls, value: str | None) -> str | None:
        if value is None:
            return value
        prefix = "data:image/jpeg;base64,"
        if not value.startswith(prefix):
            raise ValueError("Playlist covers must be JPEG images.")
        try:
            image = base64.b64decode(value[len(prefix):], validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("Playlist cover image is invalid.") from error
        if not image or len(image) > 650_000:
            raise ValueError("Playlist cover image is too large.")
        return value


class PlaylistSoundRead(ORMModel):
    sound: SoundRead
    position: int
    added_at: datetime


class PlaylistRead(ORMModel):
    id: int
    name: str
    description: str | None
    cover_image: str | None
    created_at: datetime
    updated_at: datetime
    items: list[PlaylistSoundRead]


class AddSoundRequest(ORMModel):
    sound_id: int = Field(gt=0)


class ReorderRequest(ORMModel):
    sound_ids: list[int]
