"""Recompute the classification columns of every stored post, e.g. after changing the rules.

    python -m collector.reclassify --dry-run   # summary only
    python -m collector.reclassify             # writes contest_score / categories / entry_type / deadline

No Instagram call. is_hidden (manual moderation) and author_username are never touched.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter

from collector.analyze import analyze
from collector.config import ConfigError, Settings
from collector.detect import VISIBLE_THRESHOLD
from collector.main import setup_logging
from collector.store import SupabaseStore

log = logging.getLogger("collector")

# every NOT NULL column is sent back unchanged: PostgREST upserts are INSERT … ON CONFLICT
COLUMNS = "ig_media_id,permalink,caption,caption_hash,media_type,published_at,source_hashtags"


def reclassify(store: SupabaseStore, *, dry_run: bool) -> Counter:
    stats: Counter = Counter()
    rows = []
    for post in store.iter_posts(COLUMNS):
        row = {**post, **analyze(post["caption"], post["published_at"], post["source_hashtags"] or [])}
        rows.append(row)
        stats["posts"] += 1
        stats["affichés" if row["contest_score"] >= VISIBLE_THRESHOLD else "écartés"] += 1
        stats["avec date limite"] += row["deadline"] is not None
    if not dry_run and rows:
        store.upsert_posts(rows)
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reclasse toutes les publications en base")
    parser.add_argument("--dry-run", action="store_true", help="affiche le bilan sans écrire")
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(f"Configuration invalide : {exc}", file=sys.stderr)
        return 2
    setup_logging(settings)
    stats = reclassify(SupabaseStore(settings.supabase_url, settings.supabase_secret_key), dry_run=args.dry_run)
    log.info("%s%s", "[dry-run] " if args.dry_run else "", ", ".join(f"{k} : {v}" for k, v in stats.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
