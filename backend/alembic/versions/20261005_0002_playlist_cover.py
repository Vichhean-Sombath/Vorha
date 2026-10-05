"""Add custom cover images to playlists.

Revision ID: 20261005_0002
Revises: 20261005_0001
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa


revision = "20261005_0002"
down_revision = "20261005_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("playlists", sa.Column("cover_image", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("playlists", "cover_image")
