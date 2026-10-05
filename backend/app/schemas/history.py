from datetime import datetime

from pydantic import Field

from app.schemas.common import ORMModel
from app.schemas.sound import SoundRead


class HistoryUpsert(ORMModel):
    sound_id: int = Field(gt=0)
    progress_seconds: int = Field(default=0, ge=0)
    completed: bool = False


class HistoryPatch(ORMModel):
    progress_seconds: int = Field(ge=0)
    completed: bool = False


class HistoryRead(ORMModel):
    sound: SoundRead
    progress_seconds: int
    completed: bool
    last_played_at: datetime
