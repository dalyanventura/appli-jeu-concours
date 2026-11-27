"""Instagram (Facebook Login) token: daily health check and guided renewal.

    python -m collector.ig_token check   # CI, daily: fails when the token expires within 7 days
    python -m collector.ig_token renew   # on your PC: paste a fresh token from Graph API Explorer

Why no silent auto-refresh: a Facebook user token has two deadlines, `expires_at` (~60 days) and
`data_access_expires_at` (90 days after the user last logged in). Re-exchanging the token cannot
push back the second one, so a human login is needed at least every 90 days anyway. The daily check
makes the workflow fail (GitHub then emails the repo owner) well before either deadline.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

import httpx

from collector.config import ROOT_DIR, load_dotenv

GRAPH = "https://graph.facebook.com"
WARN_DAYS = 14
FAIL_DAYS = 7
REQUIRED_SCOPES = {"instagram_basic", "instagram_manage_insights", "pages_read_engagement"}


class TokenCheckError(RuntimeError):
    pass


def debug_token(token: str, version: str, *, http: httpx.Client | None = None) -> dict:
    """A user token may inspect itself: no app secret needed."""
    client = http or httpx.Client(timeout=30)
    try:
        resp = client.get(f"{GRAPH}/{version}/debug_token", params={"input_token": token, "access_token": token})
    except httpx.HTTPError as exc:
        raise TokenCheckError(f"debug_token : erreur réseau ({type(exc).__name__})") from None
    data = resp.json() if resp.content else {}
    if resp.status_code != 200 or "data" not in data:
        message = (data.get("error") or {}).get("message", f"HTTP {resp.status_code}")
        raise TokenCheckError(f"debug_token a échoué : {message}")
    return data["data"]


def days_left(info: dict, now: datetime) -> tuple[float | None, str]:
    """Days before the earliest deadline (None = no deadline) and its name."""
    deadlines = {name: info.get(key) for name, key in
                 (("expiration du token", "expires_at"), ("expiration de l'accès aux données", "data_access_expires_at"))}
    dated = {name: ts for name, ts in deadlines.items() if ts}   # 0 means "never"
    if not dated:
        return None, "aucune"
    name, ts = min(dated.items(), key=lambda kv: kv[1])
    return (datetime.fromtimestamp(ts, timezone.utc) - now).total_seconds() / 86400, name


def check(token: str, version: str, now: datetime, *, http: httpx.Client | None = None) -> tuple[int, str]:
    """(exit code, message). 1 = act now; 0 = fine (message may still be a warning)."""
    info = debug_token(token, version, http=http)
    if not info.get("is_valid"):
        return 1, "Token Instagram invalide : lancez « python -m collector.ig_token renew »."
    missing = REQUIRED_SCOPES - set(info.get("scopes") or [])
    if missing:
        return 1, f"Permissions manquantes sur le token : {', '.join(sorted(missing))}."
    left, which = days_left(info, now)
    if left is None:
        return 0, "Token sans date d'expiration."
    message = f"{which} dans {left:.0f} jours"
    if left < FAIL_DAYS:
        return 1, f"À renouveler MAINTENANT : {message}. Lancez « python -m collector.ig_token renew »."
    if left < WARN_DAYS:
        return 0, f"À renouveler bientôt : {message}."
    return 0, f"Token OK : {message}."


def exchange(short_token: str, app_id: str, app_secret: str, version: str,
             *, http: httpx.Client | None = None) -> str:
    client = http or httpx.Client(timeout=30)
    try:
        resp = client.get(f"{GRAPH}/{version}/oauth/access_token", params={
            "grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": app_secret,
            "fb_exchange_token": short_token})
    except httpx.HTTPError as exc:
        raise TokenCheckError(f"échange du token : erreur réseau ({type(exc).__name__})") from None
    data = resp.json() if resp.content else {}
    if resp.status_code != 200 or "access_token" not in data:
        message = (data.get("error") or {}).get("message", f"HTTP {resp.status_code}")
        raise TokenCheckError(f"échange du token refusé : {message}")
    return data["access_token"]


def replace_env_value(text: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    return pattern.sub(lambda _: line, text) if pattern.search(text) else text.rstrip("\n") + f"\n{line}\n"


def renew(version: str) -> int:
    app_id, app_secret = os.environ.get("META_APP_ID"), os.environ.get("META_APP_SECRET")
    if not (app_id and app_secret):
        print("Remplissez META_APP_ID et META_APP_SECRET dans .env (Meta for Developers → votre app → "
              "Paramètres de l'app → Général).", file=sys.stderr)
        return 2
    print("Graph API Explorer → votre app → « Générer un token d'accès » avec les permissions :\n  "
          + ", ".join(sorted(REQUIRED_SCOPES | {"pages_show_list"})) + " (+ celles de la phase 0)")
    short = getpass.getpass("Collez le token (il ne s'affiche pas) : ").strip()
    long_token = exchange(short, app_id, app_secret, version)
    code, message = check(long_token, version, datetime.now(timezone.utc))
    print(message)
    if code:
        return code
    env_path = ROOT_DIR / ".env"
    env_path.write_text(replace_env_value(env_path.read_text(encoding="utf-8"), "IG_ACCESS_TOKEN", long_token),
                        encoding="utf-8")
    print("✓ .env mis à jour")
    if shutil.which("gh"):
        result = subprocess.run(["gh", "secret", "set", "IG_ACCESS_TOKEN"], input=long_token, text=True,
                                cwd=ROOT_DIR, capture_output=True)
        print("✓ secret GitHub IG_ACCESS_TOKEN mis à jour" if result.returncode == 0
              else "✗ secret GitHub non mis à jour : gh secret set IG_ACCESS_TOKEN")
    else:
        print("gh introuvable : mettez à jour le secret IG_ACCESS_TOKEN à la main sur GitHub.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vérifie ou renouvelle le token Instagram")
    parser.add_argument("action", choices=["check", "renew"])
    args = parser.parse_args(argv)
    load_dotenv()
    version = os.environ.get("GRAPH_API_VERSION", "v27.0")
    try:
        if args.action == "renew":
            return renew(version)
        token = os.environ.get("IG_ACCESS_TOKEN")
        if not token:
            print("IG_ACCESS_TOKEN manquant", file=sys.stderr)
            return 2
        code, message = check(token, version, datetime.now(timezone.utc))
    except TokenCheckError as exc:
        code, message = 1, str(exc)
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::{'error' if code else 'warning' if 'bientôt' in message else 'notice'}::{message}")
    else:
        print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
