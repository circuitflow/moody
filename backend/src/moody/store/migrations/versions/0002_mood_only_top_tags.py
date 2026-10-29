"""Recompute top_tags from mood tags only (drop theme tags such as christmas/film).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-29
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copy of moody.analysis.analyzer as of this revision (migrations must not change
# behaviour when application code changes later).
MOOD_TAGS = frozenset(
    {
        "calm", "cool", "dark", "deep", "dramatic", "dream", "emotional", "energetic", "epic",
        "fun", "funny", "groovy", "happy", "heavy", "hopeful", "inspiring", "love", "meditative",
        "melancholic", "motivational", "party", "positive", "powerful", "relaxing", "romantic",
        "sad", "sexy", "soft", "upbeat", "uplifting",
    }
)  # fmt: skip
TAG_THRESHOLD = 0.1
TOP_TAGS = 5


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT track_id, tag_probs FROM analyses")).fetchall()
    for track_id, raw in rows:
        probs: dict[str, float] = json.loads(raw) if isinstance(raw, str) else (raw or {})
        moods = sorted(
            ((t, p) for t, p in probs.items() if t in MOOD_TAGS), key=lambda kv: kv[1], reverse=True
        )
        top = " ".join(t for t, p in moods[:TOP_TAGS] if p >= TAG_THRESHOLD)
        conn.execute(
            sa.text("UPDATE analyses SET top_tags = :top WHERE track_id = :id"),
            {"top": top, "id": track_id},
        )


def downgrade() -> None:
    # Data-only migration; the previous top_tags are recomputed on the next re-analysis.
    pass
