from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import Favorite, Sound, User
from app.schemas.sound import SoundRead

router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.get("", response_model=list[SoundRead])
def list_favorites(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[Sound]:
    return list(db.scalars(select(Sound).join(Favorite).where(Favorite.user_id == user.id).order_by(Favorite.created_at.desc())).all())


@router.post("/{sound_id}", status_code=204)
def add_favorite(sound_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    sound = db.get(Sound, sound_id)
    if not sound:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Sound not found."})
    if not db.scalar(select(Favorite.id).where(Favorite.user_id == user.id, Favorite.sound_id == sound_id)):
        db.add(Favorite(user_id=user.id, sound_id=sound_id))
        db.commit()


@router.delete("/{sound_id}", status_code=204)
def remove_favorite(sound_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    favorite = db.scalar(select(Favorite).where(Favorite.user_id == user.id, Favorite.sound_id == sound_id))
    if favorite:
        db.delete(favorite)
        db.commit()
