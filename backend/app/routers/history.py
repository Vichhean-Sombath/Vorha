from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import ListeningHistory, Sound, User
from app.schemas.history import HistoryPatch, HistoryRead, HistoryUpsert

router = APIRouter(prefix="/history", tags=["listening history"])


@router.get("", response_model=list[HistoryRead])
def list_history(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[ListeningHistory]:
    return list(db.scalars(select(ListeningHistory).options(selectinload(ListeningHistory.sound)).where(ListeningHistory.user_id == user.id).order_by(ListeningHistory.last_played_at.desc()).limit(100)).all())


@router.post("", response_model=HistoryRead)
def record_history(payload: HistoryUpsert, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ListeningHistory:
    sound = db.get(Sound, payload.sound_id)
    if not sound:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Sound not found."})
    item = db.scalar(select(ListeningHistory).where(ListeningHistory.user_id == user.id, ListeningHistory.sound_id == sound.id))
    if item is None:
        item = ListeningHistory(user_id=user.id, sound_id=sound.id)
        db.add(item)
    item.progress_seconds = payload.progress_seconds
    item.completed = payload.completed
    item.last_played_at = datetime.now(timezone.utc)
    db.commit()
    return db.scalar(select(ListeningHistory).options(selectinload(ListeningHistory.sound)).where(ListeningHistory.id == item.id))


@router.patch("/{sound_id}", response_model=HistoryRead)
def update_history(sound_id: int, payload: HistoryPatch, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ListeningHistory:
    item = db.scalar(select(ListeningHistory).where(ListeningHistory.user_id == user.id, ListeningHistory.sound_id == sound_id))
    if not item:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Listening history entry not found."})
    item.progress_seconds = payload.progress_seconds
    item.completed = payload.completed
    item.last_played_at = datetime.now(timezone.utc)
    db.commit()
    return db.scalar(select(ListeningHistory).options(selectinload(ListeningHistory.sound)).where(ListeningHistory.id == item.id))


@router.delete("", status_code=204)
def clear_history(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    db.query(ListeningHistory).filter(ListeningHistory.user_id == user.id).delete(synchronize_session=False)
    db.commit()
