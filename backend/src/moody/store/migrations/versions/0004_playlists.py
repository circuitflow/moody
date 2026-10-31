"""playlists

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-31 16:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "playlists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("start_valence", sa.Double(), nullable=False),
        sa.Column("start_arousal", sa.Double(), nullable=False),
        sa.Column("end_valence", sa.Double(), nullable=False),
        sa.Column("end_arousal", sa.Double(), nullable=False),
        sa.Column("via_valence", sa.Double(), nullable=True),
        sa.Column("via_arousal", sa.Double(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "playlist_items",
        sa.Column("playlist_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["playlist_id"], ["playlists.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["track_id"], ["tracks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("playlist_id", "position"),
    )
    op.create_index("ix_playlist_items_track_id", "playlist_items", ["track_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_playlist_items_track_id", table_name="playlist_items")
    op.drop_table("playlist_items")
    op.drop_table("playlists")
