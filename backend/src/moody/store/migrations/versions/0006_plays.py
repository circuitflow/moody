"""plays

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-31 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plays",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("played_at", sa.DateTime(), nullable=False),
        sa.Column("artist", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("album", sa.Text(), nullable=True),
        sa.Column("ms_played", sa.Integer(), nullable=True),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("mbid", sa.String(length=36), nullable=True),
        sa.Column("track_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["track_id"], ["tracks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plays_source", "plays", ["source"], unique=False)
    op.create_index("ix_plays_played_at", "plays", ["played_at"], unique=False)
    op.create_index("ix_plays_track_id", "plays", ["track_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_plays_track_id", table_name="plays")
    op.drop_index("ix_plays_played_at", table_name="plays")
    op.drop_index("ix_plays_source", table_name="plays")
    op.drop_table("plays")
