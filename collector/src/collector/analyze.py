"""Classification columns of a `posts` row, computed from its caption (deterministic, rules only)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from collector.classify import classify
from collector.deadline import extract_deadline
from collector.detect import detect

ANALYSIS_COLUMNS = ("contest_score", "entry_type", "categories", "deadline")


def analyze(caption: str | None, published_at: str | datetime, source_hashtags: Iterable[str] = ()) -> dict:
    published = datetime.fromisoformat(published_at) if isinstance(published_at, str) else published_at
    detection = detect(caption)
    deadline = extract_deadline(caption, published.date())
    return {
        "contest_score": detection.score,
        "entry_type": detection.entry_type,
        "categories": classify(caption, source_hashtags),
        "deadline": deadline.isoformat() if deadline else None,
    }
