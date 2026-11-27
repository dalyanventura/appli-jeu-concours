"""Export stored posts to collector/probe_output/posts.jsonl to tune detection/classification rules.

Usage (from collector/):
    .venv/Scripts/python scripts/export_sample.py [limit]

Reads with the secret key from ../.env; prints nothing secret. The output folder is git-ignored.
"""

from __future__ import annotations

import json
import sys

import httpx

from collector.config import ROOT_DIR, Settings

OUT = ROOT_DIR / "collector" / "probe_output" / "posts.jsonl"
COLUMNS = ("ig_media_id,permalink,caption,author_username,source_hashtags,published_at,"
           "categories,contest_score,entry_type,deadline")


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    s = Settings.from_env()
    headers = {"apikey": s.supabase_secret_key}
    if s.supabase_secret_key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {s.supabase_secret_key}"
    resp = httpx.get(f"{s.supabase_url.rstrip('/')}/rest/v1/posts", headers=headers, timeout=60,
                     params={"select": COLUMNS, "order": "published_at.desc", "limit": str(limit)})
    resp.raise_for_status()
    rows = resp.json()
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{len(rows)} publications exportées dans {OUT}")


if __name__ == "__main__":
    main()
