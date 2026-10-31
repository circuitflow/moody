"""track duplicate_of

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-31 10:32:18.870480
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Not batch mode: that would rebuild `tracks` (copy, drop, rename) for one nullable column.
    # SQLite's ALTER TABLE ADD COLUMN accepts an inline REFERENCES clause when the default is
    # NULL, so the column is added in place.
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "ALTER TABLE tracks ADD COLUMN duplicate_of INTEGER "
            "REFERENCES tracks (id) ON DELETE SET NULL"
        )
    else:
        op.add_column("tracks", sa.Column("duplicate_of", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_tracks_duplicate_of",
            "tracks",
            "tracks",
            ["duplicate_of"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_tracks_duplicate_of", "tracks", ["duplicate_of"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tracks_duplicate_of", table_name="tracks")
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("fk_tracks_duplicate_of", "tracks", type_="foreignkey")
    # SQLite >= 3.35 drops a column in place (no table rebuild, so no cascade).
    op.drop_column("tracks", "duplicate_of")
