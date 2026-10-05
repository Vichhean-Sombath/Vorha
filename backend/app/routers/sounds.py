import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_optional_user
from app.core.security import stream_signature_matches
from app.models import Favorite, ListeningHistory, Playlist, PlaylistSound, Sound, User
from app.schemas.sound import AnalyzeRequest, SoundPage, SoundRead
from app.services import audio_service
from app.services.audio_service import AudioExtractionError, ExtractedAudio
from app.services.tiktok_service import TikTokService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sounds", tags=["sounds"])
limiter = Limiter(key_func=get_remote_address)
tiktok_service = TikTokService()

METADATA_FIELDS = ("title", "creator_name", "creator_username", "thumbnail_url", "duration_seconds", "playback_url", "is_playable")


def stream_path(sound_id: int) -> str:
    return f"/sounds/{sound_id}/stream"


def _apply_audio(db: Session, sound: Sound, extracted: ExtractedAudio) -> None:
    sound.playback_url = stream_path(sound.id)
    sound.is_playable = True
    if extracted.duration_seconds:
        # A fresh extraction probed the real file, so it outranks any stored value.
        # A warm cache hit reports None and leaves the known duration alone.
        sound.duration_seconds = extracted.duration_seconds
    db.add(sound)
    db.commit()
    db.refresh(sound)


def _http_error(error: AudioExtractionError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail={"code": error.code, "message": error.message})


def _load_sound(db: Session, sound_id: int) -> Sound:
    sound = db.get(Sound, sound_id)
    if not sound:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Sound not found."})
    return sound


def _require_key(sound: Sound) -> str:
    key = audio_service.normalize_key(sound.external_id)
    if not key:
        raise HTTPException(status_code=422, detail={"code": "AUDIO_UNAVAILABLE", "message": "This sound has no video identifier to fetch audio for."})
    return key


async def _extract_or_none(db: Session, sound: Sound) -> bool:
    """Best-effort audio preparation used while analyzing a link."""
    key = audio_service.normalize_key(sound.external_id)
    if not key:
        return False
    try:
        extracted = await audio_service.ensure_audio(sound.source_url, key)
    except AudioExtractionError as error:
        logger.info("Audio unavailable for sound %s (%s): %s", sound.id, error.code, error.message)
        return False
    _apply_audio(db, sound, extracted)
    return True


@router.post("/analyze", response_model=SoundRead)
@limiter.limit("5/minute")
async def analyze(request: Request, payload: AnalyzeRequest, db: Session = Depends(get_db)) -> Sound:
    source_url = tiktok_service.validate_url(str(payload.url))
    metadata = await tiktok_service.analyze(source_url)
    sound = None
    if metadata.external_id:
        sound = db.scalar(select(Sound).where(Sound.source_platform == "tiktok", Sound.external_id == metadata.external_id))
    if sound is None:
        sound = Sound(source_platform="tiktok", source_url=metadata.source_url, external_id=metadata.external_id)
    for field in METADATA_FIELDS:
        value = getattr(metadata, field)
        if field == "duration_seconds" and value is None:
            continue  # oEmbed omits duration; keep what a previous extraction recorded
        setattr(sound, field, value)
    sound.source_url = metadata.source_url
    db.add(sound)
    db.commit()
    db.refresh(sound)
    await _extract_or_none(db, sound)
    return sound


@router.post("/{sound_id}/audio", response_model=SoundRead)
@limiter.limit("10/minute")
async def prepare_audio(request: Request, sound_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Sound:
    """Extract (or re-extract) the audio track for a saved sound and report why it failed."""
    sound = _load_sound(db, sound_id)
    key = _require_key(sound)
    try:
        extracted = await audio_service.ensure_audio(sound.source_url, key)
    except AudioExtractionError as error:
        raise _http_error(error) from None
    _apply_audio(db, sound, extracted)
    return sound


@router.get("/{sound_id}/stream")
@limiter.limit("120/minute")
async def stream_audio(
    request: Request,
    sound_id: int,
    t: str | None = Query(default=None, max_length=64),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> FileResponse:
    """Serve the cached audio-only track, supporting byte-range requests for seeking.

    Accepts either a signed-in session or the signed token issued with the sound,
    so guests can play a link they just analyzed without the endpoint becoming
    enumerable or letting anonymous callers trigger extraction.
    """
    sound = _load_sound(db, sound_id)
    if user is None and not stream_signature_matches(t, sound.id, sound.external_id):
        raise HTTPException(status_code=401, detail={"code": "PLAYBACK_FORBIDDEN", "message": "This playback link is no longer valid. Look the sound up again."})
    key = _require_key(sound)
    if not audio_service.has_cached_audio(key):
        try:
            extracted = await audio_service.ensure_audio(sound.source_url, key)
        except AudioExtractionError as error:
            raise _http_error(error) from None
        _apply_audio(db, sound, extracted)
    return FileResponse(
        audio_service.audio_path(key),
        media_type=audio_service.AUDIO_MEDIA_TYPE,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=3600", "Accept-Ranges": "bytes"},
    )


@router.get("", response_model=SoundPage)
def list_sounds(
    q: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SoundPage:
    saved_ids = select(Favorite.sound_id).where(Favorite.user_id == user.id).union(
        select(PlaylistSound.sound_id).join(Playlist).where(Playlist.user_id == user.id),
        select(ListeningHistory.sound_id).where(ListeningHistory.user_id == user.id),
    )
    query = select(Sound).where(Sound.id.in_(saved_ids))
    count_query = select(func.count()).select_from(Sound).where(Sound.id.in_(saved_ids))
    if q:
        term = f"%{q.strip()}%"
        clause = or_(Sound.title.ilike(term), Sound.creator_name.ilike(term), Sound.creator_username.ilike(term))
        query = query.where(clause)
        count_query = count_query.where(clause)
    total = db.scalar(count_query) or 0
    items = list(db.scalars(query.order_by(Sound.updated_at.desc()).offset((page - 1) * limit).limit(limit)).all())
    return SoundPage(items=items, page=page, limit=limit, total=total)


@router.get("/{sound_id}", response_model=SoundRead)
def get_sound(sound_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Sound:
    return _load_sound(db, sound_id)
