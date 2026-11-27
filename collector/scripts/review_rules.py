"""Apply the phase 3 rules to the exported posts and write a CSV to review in Excel/LibreOffice.

Usage (from collector/, after scripts/export_sample.py):
    .venv/Scripts/python scripts/review_rules.py

Output: probe_output/review.csv (separator ";", UTF-8 with BOM for Excel) + a summary.
"""

from __future__ import annotations

import csv
import json
from collections import Counter

from collector.analyze import analyze
from collector.config import ROOT_DIR
from collector.detect import VISIBLE_THRESHOLD, detect

OUT_DIR = ROOT_DIR / "collector" / "probe_output"


def main() -> None:
    rows = [json.loads(line) for line in (OUT_DIR / "posts.jsonl").open(encoding="utf-8")]
    visible, entry_types, categories, with_deadline = 0, Counter(), Counter(), 0
    with (OUT_DIR / "review.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["affiché", "score", "signaux", "participation", "thèmes", "date limite",
                         "compte", "lien", "légende"])
        for row in sorted(rows, key=lambda r: -analyze(r["caption"], r["published_at"])["contest_score"]):
            result = analyze(row["caption"], row["published_at"], row.get("source_hashtags") or [])
            shown = result["contest_score"] >= VISIBLE_THRESHOLD
            if shown:
                visible += 1
                entry_types[result["entry_type"]] += 1
                categories.update(result["categories"])
                with_deadline += result["deadline"] is not None
            writer.writerow([
                "oui" if shown else "non", result["contest_score"], " ".join(detect(row["caption"]).signals),
                result["entry_type"], ", ".join(result["categories"]), result["deadline"] or "",
                row.get("author_username") or "", row.get("permalink") or "",
                (row["caption"] or "").replace("\n", " ⏎ ")[:400],
            ])
    print(f"{visible}/{len(rows)} affichés (score ≥ {VISIBLE_THRESHOLD}), dont {with_deadline} avec date limite")
    print("Participation :", dict(entry_types.most_common()))
    print("Thèmes :", dict(categories.most_common()))
    print(f"Détail : {OUT_DIR / 'review.csv'}")


if __name__ == "__main__":
    main()
