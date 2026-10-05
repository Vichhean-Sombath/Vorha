from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import Playlist, PlaylistSound, Sound, User
from app.schemas.playlist import AddSoundRequest, PlaylistCreate, PlaylistPatch, PlaylistRead, ReorderRequest

router = APIRouter(prefix="/playlists", tags=["playlists"])


def _owned_playlist(db: Session, user_id: int, playlist_id: int) -> Playlist:
    playlist = db.scalar(select(Playlist).options(selectinload(Playlist.items).selectinload(PlaylistSound.sound)).where(Playlist.id == playlist_id, Playlist.user_id == user_id).execution_options(populate_existing=True))
    if not playlist:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Playlist not found."})
    return playlist


@router.get("", response_model=list[PlaylistRead])
def list_playlists(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[Playlist]:
    return list(db.scalars(select(Playlist).options(selectinload(Playlist.items).selectinload(PlaylistSound.sound)).where(Playlist.user_id == user.id).order_by(Playlist.updated_at.desc())).all())


@router.post("", response_model=PlaylistRead, status_code=201)
def create_playlist(payload: PlaylistCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Playlist:
    playlist = Playlist(user_id=user.id, name=payload.name.strip(), description=payload.description)
    db.add(playlist)
    db.commit()
    return _owned_playlist(db, user.id, playlist.id)


@router.get("/{playlist_id}", response_model=PlaylistRead)
def get_playlist(playlist_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Playlist:
    return _owned_playlist(db, user.id, playlist_id)


@router.patch("/{playlist_id}", response_model=PlaylistRead)
def update_playlist(playlist_id: int, payload: PlaylistPatch, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Playlist:
    playlist = _owned_playlist(db, user.id, playlist_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(playlist, key, value.strip() if key == "name" and value is not None else value)
    db.commit()
    return _owned_playlist(db, user.id, playlist_id)


@router.delete("/{playlist_id}", status_code=204)
def delete_playlist(playlist_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    playlist = _owned_playlist(db, user.id, playlist_id)
    db.delete(playlist)
    db.commit()


@router.post("/{playlist_id}/sounds", response_model=PlaylistRead, status_code=201)
def add_sound(playlist_id: int, payload: AddSoundRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Playlist:
    playlist = _owned_playlist(db, user.id, playlist_id)
    sound = db.get(Sound, payload.sound_id)
    if not sound:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Sound not found."})
    existing = db.scalar(select(PlaylistSound).where(PlaylistSound.playlist_id == playlist_id, PlaylistSound.sound_id == sound.id))
    if not existing:
        next_position = db.scalar(select(func.coalesce(func.max(PlaylistSound.position), -1) + 1).where(PlaylistSound.playlist_id == playlist_id)) or 0
        db.add(PlaylistSound(playlist_id=playlist_id, sound_id=sound.id, position=next_position))
        db.commit()
    return _owned_playlist(db, user.id, playlist_id)


@router.delete("/{playlist_id}/sounds/{sound_id}", status_code=204)
def remove_sound(playlist_id: int, sound_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    _owned_playlist(db, user.id, playlist_id)
    entry = db.scalar(select(PlaylistSound).where(PlaylistSound.playlist_id == playlist_id, PlaylistSound.sound_id == sound_id))
    if entry:
        db.delete(entry)
        db.commit()
        entries = list(db.scalars(select(PlaylistSound).where(PlaylistSound.playlist_id == playlist_id).order_by(PlaylistSound.position)).all())
        for position, item in enumerate(entries):
            item.position = -position - 1
        db.flush()
        for position, item in enumerate(entries):
            item.position = position
        db.commit()


@router.patch("/{playlist_id}/reorder", response_model=PlaylistRead)
def reorder(playlist_id: int, payload: ReorderRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Playlist:
    playlist = _owned_playlist(db, user.id, playlist_id)
    by_sound = {item.sound_id: item for item in playlist.items}
    if len(payload.sound_ids) != len(set(payload.sound_ids)) or set(payload.sound_ids) != set(by_sound):
        raise HTTPException(status_code=422, detail={"code": "VALIDATION_ERROR", "message": "Provide each playlist sound exactly once."})
    for position, sound_id in enumerate(payload.sound_ids):
        by_sound[sound_id].position = -position - 1
    db.flush()
    for position, sound_id in enumerate(payload.sound_ids):
        by_sound[sound_id].position = position
    db.commit()
    return _owned_playlist(db, user.id, playlist_id)
