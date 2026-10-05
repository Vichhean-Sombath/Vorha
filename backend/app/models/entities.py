from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import BigInteger as BigIntegerType

from app.core.database import Base

ID_TYPE = BigIntegerType().with_variant(Integer, "sqlite")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=func.now(), server_default=func.now())


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    playlists: Mapped[list["Playlist"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    favorites: Mapped[list["Favorite"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    listening_history: Mapped[list["ListeningHistory"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Sound(TimestampMixin, Base):
    __tablename__ = "sounds"
    __table_args__ = (UniqueConstraint("source_platform", "external_id", name="uq_sound_source_external"),)
    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    source_platform: Mapped[str] = mapped_column(String(30), default="tiktok", index=True)
    source_url: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    creator_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    creator_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    playback_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_playable: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    playlist_entries: Mapped[list["PlaylistSound"]] = relationship(back_populates="sound", cascade="all, delete-orphan")
    favorites: Mapped[list["Favorite"]] = relationship(back_populates="sound", cascade="all, delete-orphan")
    history_entries: Mapped[list["ListeningHistory"]] = relationship(back_populates="sound", cascade="all, delete-orphan")


class Playlist(TimestampMixin, Base):
    __tablename__ = "playlists"
    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    user: Mapped[User] = relationship(back_populates="playlists")
    items: Mapped[list["PlaylistSound"]] = relationship(back_populates="playlist", cascade="all, delete-orphan", order_by="PlaylistSound.position")


class PlaylistSound(Base):
    __tablename__ = "playlist_sounds"
    __table_args__ = (UniqueConstraint("playlist_id", "sound_id", name="uq_playlist_sound"), UniqueConstraint("playlist_id", "position", name="uq_playlist_position"))
    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    playlist_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("playlists.id", ondelete="CASCADE"), index=True)
    sound_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("sounds.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now())
    playlist: Mapped[Playlist] = relationship(back_populates="items")
    sound: Mapped[Sound] = relationship(back_populates="playlist_entries")


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "sound_id", name="uq_favorite_user_sound"),)
    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    sound_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("sounds.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now())
    user: Mapped[User] = relationship(back_populates="favorites")
    sound: Mapped[Sound] = relationship(back_populates="favorites")


class ListeningHistory(Base):
    __tablename__ = "listening_history"
    __table_args__ = (UniqueConstraint("user_id", "sound_id", name="uq_history_user_sound"),)
    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    sound_id: Mapped[int] = mapped_column(ID_TYPE, ForeignKey("sounds.id", ondelete="CASCADE"), index=True)
    progress_seconds: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    last_played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), index=True)
    user: Mapped[User] = relationship(back_populates="listening_history")
    sound: Mapped[Sound] = relationship(back_populates="history_entries")
