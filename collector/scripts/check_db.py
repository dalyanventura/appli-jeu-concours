"""Phase 1 check: verify the Supabase schema and that RLS lets the app read but not write.

Usage:
    python collector/scripts/check_db.py

Needs SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY and SUPABASE_SECRET_KEY in ./.env.
Inserts one fake post with the secret key, checks what the public key sees, then deletes it.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST_ID = "__check_db_test__"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def rest(method: str, path: str, key: str, body: object | None = None) -> tuple[int, object]:
    url = f"{os.environ['SUPABASE_URL'].rstrip('/')}/rest/v1/{path}"
    headers = {"apikey": key, "Content-Type": "application/json", "Prefer": "return=representation"}
    if key.startswith("eyJ"):  # legacy JWT keys (anon / service_role) also need a Bearer header
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw.decode(errors="replace")


failures = 0


def check(ok: bool, label: str, detail: object = "") -> None:
    global failures
    print(f"  {'✓' if ok else '✗'} {label}" + (f" — {detail}" if detail and not ok else ""))
    failures += 0 if ok else 1


def main() -> None:
    load_env(ROOT / ".env")
    missing = [k for k in ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SECRET_KEY") if not os.environ.get(k)]
    if missing:
        sys.exit(f"✗ Variables manquantes dans .env : {', '.join(missing)}")
    public, secret = os.environ["SUPABASE_PUBLISHABLE_KEY"], os.environ["SUPABASE_SECRET_KEY"]

    print("1) Lecture publique des thèmes")
    status, data = rest("GET", "categories?select=slug&order=sort_order", public)
    check(status == 200 and isinstance(data, list) and len(data) == 17, "17 thèmes lisibles", (status, data))

    print("2) Écriture refusée avec la clé publique")
    fake = {"ig_media_id": TEST_ID, "permalink": "https://example.invalid", "caption_hash": TEST_ID,
            "media_type": "IMAGE", "published_at": "2026-11-27T12:00:00Z"}
    status, data = rest("POST", "posts", public, fake)
    check(status in (401, 403), "insertion dans posts refusée", (status, data))
    status, data = rest("GET", "hashtags?select=tag", public)
    check(status in (401, 403) or data == [], "table hashtags invisible", (status, data))

    status, data = rest("GET", "accounts?select=username", public)
    check(status == 200, "noms des comptes suivis lisibles (migration accounts appliquée)", (status, data))
    status, data = rest("GET", "accounts?select=last_error", public)
    check(status in (401, 403), "détails internes des comptes invisibles", (status, data))
    status, data = rest("GET", "account_suggestions?select=username,is_business,recent_contests", secret)
    check(status == 200, "table account_suggestions à jour (migrations appliquées)", (status, data))
    status, data = rest("GET", "account_suggestions?select=username", public)
    check(status in (401, 403) or data == [], "suggestions de comptes invisibles", (status, data))

    print("3) Écriture avec la clé secrète (collecteur)")
    status, data = rest("POST", "posts", secret, {**fake, "categories": ["autre"], "contest_score": 0.9})
    check(status == 201, "post de test inséré", (status, data))

    print("4) Visibilité côté app")
    status, data = rest("GET", f"posts?ig_media_id=eq.{TEST_ID}&select=ig_media_id", public)
    check(status == 200 and len(data) == 1, "post visible avec la clé publique", (status, data))
    rest("PATCH", f"posts?ig_media_id=eq.{TEST_ID}", secret, {"contest_score": 0.2})
    status, data = rest("GET", f"posts?ig_media_id=eq.{TEST_ID}&select=ig_media_id", public)
    check(status == 200 and data == [], "post au score < 0.5 invisible (migration phase 3 appliquée)", (status, data))
    rest("PATCH", f"posts?ig_media_id=eq.{TEST_ID}", secret, {"contest_score": 0.9})
    status, data = rest("PATCH", f"posts?ig_media_id=eq.{TEST_ID}", secret, {"is_hidden": True})
    check(status == 200 and isinstance(data, list) and len(data) == 1 and data[0].get("is_hidden") is True,
          "masquage enregistré (clé secrète)", (status, data))
    status, data = rest("GET", f"posts?ig_media_id=eq.{TEST_ID}&select=ig_media_id,is_hidden", secret)
    print(f"    état en base vu par la clé secrète : {data}")
    status, data = rest("GET", f"posts?ig_media_id=eq.{TEST_ID}&select=ig_media_id,is_hidden", public)
    check(status == 200 and data == [], "post masqué invisible avec la clé publique", (status, data))

    print("5) Nettoyage")
    status, data = rest("DELETE", f"posts?ig_media_id=eq.{TEST_ID}", secret)
    check(status in (200, 204), "post de test supprimé", (status, data))
    status, data = rest("POST", "rpc/purge_old_posts", public, {})
    check(status in (401, 403, 404), "purge_old_posts interdite à la clé publique", (status, data))
    status, data = rest("POST", "rpc/purge_old_posts", secret, {})
    check(status == 200, "purge_old_posts autorisée au collecteur (clé secrète)", (status, data))

    print("\n✓ Phase 1 validée." if not failures else f"\n✗ {failures} vérification(s) en échec.")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
