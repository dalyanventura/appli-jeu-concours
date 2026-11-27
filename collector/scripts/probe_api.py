"""Phase 0 probe: check that Instagram hashtag search works with our Meta app and token.

Usage:
    python collector/scripts/probe_api.py                 # check token + list linked IG accounts
    python collector/scripts/probe_api.py jeuconcours     # also search one hashtag

Each distinct hashtag searched counts against the 30-unique-hashtags / 7-day quota,
so keep probing to one or two tags. Stdlib only, reads settings from ./.env.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "collector" / "probe_output"  # git-ignored: contains real captions
MEDIA_FIELDS = "id,caption,media_type,media_url,permalink,timestamp,like_count,comments_count"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def graph_get(path: str, **params: str) -> dict:
    version = os.environ.get("GRAPH_API_VERSION", "v27.0")
    params["access_token"] = os.environ["IG_ACCESS_TOKEN"]
    url = f"https://graph.facebook.com/{version}/{path.lstrip('/')}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            for header in ("X-Business-Use-Case-Usage", "X-App-Usage"):
                if resp.headers.get(header):
                    print(f"    [{header}] {resp.headers[header]}")
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            err = json.loads(body).get("error", {})
            msg = f"{err.get('type')} (code {err.get('code')}/{err.get('error_subcode')}): {err.get('message')}"
        except json.JSONDecodeError:
            msg = body
        sys.exit(f"\n✗ Erreur API sur {path} : HTTP {exc.code} — {msg}")


def main() -> None:
    load_env(ROOT / ".env")
    if not os.environ.get("IG_ACCESS_TOKEN"):
        sys.exit("✗ IG_ACCESS_TOKEN manquant : copiez .env.example en .env et remplissez-le.")

    print("1) Vérification du token…")
    me = graph_get("me", fields="id,name")
    print(f"   ✓ Token valide pour : {me.get('name')} ({me.get('id')})")

    print("2) Pages Facebook et comptes Instagram professionnels liés…")
    pages = graph_get("me/accounts", fields="name,instagram_business_account{id,username}")
    ig_accounts = []
    for page in pages.get("data", []):
        ig = page.get("instagram_business_account")
        label = f"@{ig['username']} → IG_USER_ID={ig['id']}" if ig else "aucun compte IG pro lié"
        print(f"   - Page « {page['name']} » : {label}")
        if ig:
            ig_accounts.append(ig)
    if not pages.get("data"):
        print("   ⚠ Aucune Page visible : vérifiez la permission pages_show_list sur le token.")

    ig_user_id = os.environ.get("IG_USER_ID") or (ig_accounts[0]["id"] if ig_accounts else None)
    hashtags = sys.argv[1:]
    if not hashtags:
        print("\nAucun hashtag passé en argument : arrêt ici. Exemple : python collector/scripts/probe_api.py jeuconcours")
        return
    if not ig_user_id:
        sys.exit("✗ Aucun IG_USER_ID : liez un compte Instagram pro à votre Page Facebook.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for tag in hashtags:
        tag = tag.lstrip("#").lower()
        print(f"\n3) Recherche du hashtag #{tag}…")
        found = graph_get("ig_hashtag_search", user_id=ig_user_id, q=tag)
        if not found.get("data"):
            print("   ✗ Hashtag introuvable.")
            continue
        hashtag_id = found["data"][0]["id"]
        print(f"   ✓ ID du hashtag : {hashtag_id}")

        print("4) Publications récentes (dernières 24 h)…")
        media = graph_get(f"{hashtag_id}/recent_media", user_id=ig_user_id, fields=MEDIA_FIELDS, limit="50")
        items = media.get("data", [])
        print(f"   ✓ {len(items)} publications sur la 1re page (page suivante : {'oui' if media.get('paging', {}).get('next') else 'non'})")
        for item in items[:5]:
            caption = (item.get("caption") or "").replace("\n", " ")[:90]
            print(f"   • {item.get('timestamp')} {item.get('media_type'):<14} {item.get('permalink')}\n     {caption}")
        missing_url = sum(1 for i in items if not i.get("media_url"))
        print(f"   ℹ Publications sans media_url : {missing_url}/{len(items)}")

        media.get("paging", {}).pop("next", None)  # the "next" URL embeds the access token
        out = OUTPUT_DIR / f"{tag}_{datetime.now():%Y%m%d_%H%M%S}.json"
        out.write_text(json.dumps(media, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"   Réponse brute enregistrée dans {out.relative_to(ROOT)}")

    print("\n✓ Phase 0 validée : la recherche par hashtag fonctionne.")


if __name__ == "__main__":
    main()
