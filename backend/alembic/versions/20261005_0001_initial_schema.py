"""Create Vorha's initial schema.

Revision ID: 20261005_0001
Revises:
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_username", "users", ["username"])
    op.create_table(
        "sounds",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_platform", sa.String(length=30), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("creator_name", sa.String(length=255), nullable=True),
        sa.Column("creator_username", sa.String(length=255), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("playback_url", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("is_playable", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_platform", "external_id", name="uq_sound_source_external"),
    )
    op.create_index("ix_sounds_source_platform", "sounds", ["source_platform"])
    op.create_table(
        "playlists",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_playlists_user_id", "playlists", ["user_id"])
    op.create_table(
        "favorites",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("sound_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["sound_id"], ["sounds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "sound_id", name="uq_favorite_user_sound"),
    )
    op.create_index("ix_favorites_sound_id", "favorites", ["sound_id"])
    op.create_index("ix_favorites_user_id", "favorites", ["user_id"])
    op.create_table(
        "listening_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("sound_id", sa.BigInteger(), nullable=False),
        sa.Column("progress_seconds", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_played_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["sound_id"], ["sounds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "sound_id", name="uq_history_user_sound"),
    )
    op.create_index("ix_listening_history_last_played_at", "listening_history", ["last_played_at"])
    op.create_index("ix_listening_history_sound_id", "listening_history", ["sound_id"])
    op.create_index("ix_listening_history_user_id", "listening_history", ["user_id"])
    op.create_table(
        "playlist_sounds",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("playlist_id", sa.BigInteger(), nullable=False),
        sa.Column("sound_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["playlist_id"], ["playlists.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sound_id"], ["sounds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("playlist_id", "position", name="uq_playlist_position"),
        sa.UniqueConstraint("playlist_id", "sound_id", name="uq_playlist_sound"),
    )
    op.create_index("ix_playlist_sounds_playlist_id", "playlist_sounds", ["playlist_id"])
    op.create_index("ix_playlist_sounds_sound_id", "playlist_sounds", ["sound_id"])


def downgrade() -> None:
    op.drop_index("ix_playlist_sounds_sound_id", table_name="playlist_sounds")
    op.drop_index("ix_playlist_sounds_playlist_id", table_name="playlist_sounds")
    op.drop_table("playlist_sounds")
    op.drop_index("ix_listening_history_user_id", table_name="listening_history")
    op.drop_index("ix_listening_history_sound_id", table_name="listening_history")
    op.drop_index("ix_listening_history_last_played_at", table_name="listening_history")
    op.drop_table("listening_history")
    op.drop_index("ix_favorites_user_id", table_name="favorites")
    op.drop_index("ix_favorites_sound_id", table_name="favorites")
    op.drop_table("favorites")
    op.drop_index("ix_playlists_user_id", table_name="playlists")
    op.drop_table("playlists")
    op.drop_index("ix_sounds_source_platform", table_name="sounds")
    op.drop_table("sounds")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
