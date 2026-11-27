"""One hourly collection run.

    python -m collector.main              # real run
    python -m collector.main --dry-run    # calls the API and reads the DB, writes nothing
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from collector.analyze import analyze
from collector.config import WEEKLY_HASHTAG_LIMIT, ConfigError, Settings, load_hashtag_config
from collector.instagram import (InstagramClient, InstagramError, PermissionDeniedError, RateLimitedError,
                                 TokenError, parse_timestamp)
from collector.normalize import looks_like_contest, merge_batch, partner_mentions, to_row
from collector.detect import VISIBLE_THRESHOLD
from collector.store import SupabaseStore

log = logging.getLogger("collector")

LOOKBACK = timedelta(hours=24)              # recent_media only covers the last 24 h
OVERLAP = timedelta(hours=1)                # re-read a bit before the previous run to not miss late items
FIRST_ACCOUNT_LOOKBACK = timedelta(days=7)  # first read of a newly followed account
MAX_ACCOUNTS_PER_RUN = 60                   # 1 API call each; the rest rotate to the next runs
MAX_SUGGESTION_CHECKS = 10                  # partner suggestions checked with Business Discovery per run


class QuotaGuardError(RuntimeError):
    pass


@dataclass
class RunStats:
    fetched: int = 0
    upserted: int = 0
    purged: int = 0
    partial_reason: str | None = None


def check_hashtag_quota(tags: tuple[str, ...], known: dict[str, dict], now: datetime) -> int:
    """Refuse to run if this run would exceed 30 unique hashtags over the last 7 days."""
    week_ago = now - timedelta(days=7)
    recent = {
        tag for tag, row in known.items()
        if row.get("last_collected_at") and datetime.fromisoformat(row["last_collected_at"]) > week_ago
    }
    total = recent | set(tags)
    if len(total) > WEEKLY_HASHTAG_LIMIT:
        extra = sorted(recent - set(tags))
        raise QuotaGuardError(
            f"{len(total)} hashtags uniques sur 7 jours (max {WEEKLY_HASHTAG_LIMIT}). "
            f"Tags interrogés récemment mais absents de la liste : {', '.join(extra) or 'aucun'}."
        )
    return len(total)


def collect(ig: InstagramClient, store: SupabaseStore, tags: tuple[str, ...], *,
            max_pages: int, now: datetime, dry_run: bool = False,
            max_accounts: int = MAX_ACCOUNTS_PER_RUN) -> RunStats:
    known = store.list_hashtags()
    used = check_hashtag_quota(tags, known, now)
    log.info("Hashtags uniques sur 7 jours : %d/%d", used, WEEKLY_HASHTAG_LIMIT)

    stats = RunStats()
    rows: list[dict] = []
    mentions: dict[str, set[str]] = {}
    _collect_hashtags(ig, store, tags, known, rows, stats, max_pages=max_pages, now=now, dry_run=dry_run)
    if stats.partial_reason is None:
        _collect_accounts(ig, store, rows, stats, mentions, max_accounts=max_accounts, now=now,
                          dry_run=dry_run)

    existing = store.find_existing([r["ig_media_id"] for r in rows],
                                   [r["caption_hash"] for r in rows]) if rows else []
    merged = merge_batch(rows, existing)
    log.info("%d publications retenues → %d après dédoublonnage", len(rows), len(merged))
    for row in merged:
        row.update(analyze(row["caption"], row["published_at"], row["source_hashtags"]))
    shown = sum(row["contest_score"] >= VISIBLE_THRESHOLD for row in merged)
    log.info("%d concours affichés dans l'app (score ≥ %.1f), %d écartés", shown, VISIBLE_THRESHOLD,
             len(merged) - shown)

    if mentions:
        followed = store.list_account_usernames()
        mentions = {name: by for name, by in mentions.items() if name not in followed}
        log.info("Marques partenaires suggérées : %s", ", ".join(f"@{m}" for m in sorted(mentions)) or "aucune")

    if dry_run:
        log.info("[dry-run] rien n'est écrit en base")
        return stats
    stats.upserted = store.upsert_posts(merged)
    if mentions:
        store.save_suggestions(mentions, now)
    if stats.partial_reason is None:
        _check_suggestions(ig, store, now)
    stats.purged = store.purge_old_posts()
    return stats


def _check_suggestions(ig: InstagramClient, store: SupabaseStore, now: datetime,
                       limit: int = MAX_SUGGESTION_CHECKS) -> None:
    """Keep only real professional accounts among partner suggestions, with their recent contests."""
    for username in store.list_unchecked_suggestions(limit):
        if ig.near_limit:
            return
        try:
            items = ig.discover_media(username)
        except TokenError:
            raise
        except (RateLimitedError, PermissionDeniedError) as exc:
            log.warning("Vérification des suggestions interrompue : %s", exc)
            return
        except (InstagramError, ValueError):
            store.mark_suggestion(username, now, is_business=False)
            continue
        month_ago = now - timedelta(days=30)
        contests = sum(1 for item in items if item.get("timestamp")
                       and parse_timestamp(item["timestamp"]) >= month_ago and looks_like_contest(item.get("caption")))
        store.mark_suggestion(username, now, is_business=True, recent_contests=contests)
        log.info("Suggestion @%s : compte pro, %d concours en 30 jours", username, contests)


def _collect_accounts(ig: InstagramClient, store: SupabaseStore, rows: list[dict], stats: RunStats,
                      mentions: dict[str, set[str]], *, max_accounts: int, now: datetime,
                      dry_run: bool) -> None:
    """Followed accounts via Business Discovery; only posts that look like contests are kept.

    Brands @mentioned in those contests (co-organised giveaways) are collected into `mentions`
    (suggested account → followed accounts that mentioned it).
    """
    accounts = store.list_accounts(max_accounts)
    log.info("Comptes suivis à lire : %d", len(accounts))
    for account in accounts:
        username = account["username"]
        if ig.near_limit:
            stats.partial_reason = f"quota API à {ig.usage:.0f} %, arrêt avant @{username}"
            log.warning(stats.partial_reason)
            return
        since = now - FIRST_ACCOUNT_LOOKBACK
        if account.get("last_collected_at"):
            since = datetime.fromisoformat(account["last_collected_at"]) - OVERLAP
        try:
            items = ig.discover_media(username)
        except RateLimitedError as exc:
            stats.partial_reason = f"limite de débit atteinte sur @{username} : {exc}"
            log.warning(stats.partial_reason)
            return
        except TokenError:
            raise
        except PermissionDeniedError as exc:
            # app-level problem (missing permission on the token): don't blame each account
            stats.partial_reason = (f"comptes suivis non lus, permission manquante sur le token "
                                    f"(instagram_manage_insights ?) : {exc}")
            log.warning(stats.partial_reason)
            return
        except (InstagramError, ValueError) as exc:
            # typically a personal (non-business) account, or a renamed one: skip it, keep going
            log.warning("@%s ignoré : %s", username, exc)
            if not dry_run:
                store.mark_account(username, now, error=str(exc)[:500])
            continue

        kept = 0
        for item in items:
            if not item.get("timestamp") or parse_timestamp(item["timestamp"]) < since:
                continue
            stats.fetched += 1
            if looks_like_contest(item.get("caption")) and (row := to_row(item, author=username)):
                rows.append(row)
                kept += 1
                for partner in partner_mentions(item.get("caption"), username):
                    mentions.setdefault(partner, set()).add(username)
        log.info("@%s : %d concours probables", username, kept)
        if not dry_run:
            store.mark_account(username, now)


def _collect_hashtags(ig: InstagramClient, store: SupabaseStore, tags: tuple[str, ...],
                      known: dict[str, dict], rows: list[dict], stats: RunStats, *,
                      max_pages: int, now: datetime, dry_run: bool) -> None:
    for tag in tags:
        if ig.near_limit:
            stats.partial_reason = f"quota API à {ig.usage:.0f} %, arrêt avant #{tag}"
            log.warning(stats.partial_reason)
            break
        cached = known.get(tag, {})
        count = 0
        try:
            hashtag_id = cached.get("ig_hashtag_id")
            if not hashtag_id:
                hashtag_id = ig.search_hashtag(tag)
                if hashtag_id is None:
                    log.warning("#%s introuvable sur Instagram, ignoré", tag)
                    continue
                if not dry_run:
                    store.save_hashtag_id(tag, hashtag_id)

            since = now - LOOKBACK
            if cached.get("last_collected_at"):
                since = max(since, datetime.fromisoformat(cached["last_collected_at"]) - OVERLAP)

            for item in ig.iter_recent_media(hashtag_id, since=since, max_pages=max_pages):
                count += 1
                if row := to_row(item, tag):
                    rows.append(row)
        except RateLimitedError as exc:
            stats.fetched += count
            stats.partial_reason = f"limite de débit atteinte sur #{tag} : {exc}"
            log.warning(stats.partial_reason)
            break
        stats.fetched += count
        log.info("#%s : %d publications", tag, count)
        if not dry_run:
            store.mark_collected(tag, now)


class RedactingFormatter(logging.Formatter):
    """Last line of defence: never print secrets, even inside a traceback."""

    def __init__(self, fmt: str, secrets: list[str]) -> None:
        super().__init__(fmt)
        self._secrets = [s for s in secrets if s]

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        for secret in self._secrets:
            text = text.replace(secret, "***")
        return text


def setup_logging(settings: Settings) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(message)s",
                                            [settings.ig_access_token, settings.supabase_secret_key]))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)   # httpx logs full URLs (with the token)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collecte horaire des jeux concours Instagram")
    parser.add_argument("--dry-run", action="store_true", help="appelle l'API sans écrire en base")
    parser.add_argument("--max-pages", type=int, help="remplace max_pages_per_tag de hashtags.yaml")
    parser.add_argument("--max-accounts", type=int, default=MAX_ACCOUNTS_PER_RUN,
                        help=f"comptes suivis lus par passage (défaut {MAX_ACCOUNTS_PER_RUN})")
    args = parser.parse_args(argv)

    try:
        settings = Settings.from_env()
        hashtags = load_hashtag_config()
    except ConfigError as exc:
        print(f"Configuration invalide : {exc}", file=sys.stderr)
        return 2

    setup_logging(settings)

    ig = InstagramClient(settings.ig_access_token, settings.ig_user_id, settings.graph_api_version)
    store = SupabaseStore(settings.supabase_url, settings.supabase_secret_key)
    now = datetime.now(timezone.utc)

    run_id = None if args.dry_run else store.start_run()
    try:
        stats = collect(ig, store, hashtags.tags, max_pages=args.max_pages or hashtags.max_pages_per_tag,
                        now=now, dry_run=args.dry_run, max_accounts=args.max_accounts)
    except Exception as exc:
        log.exception("Échec du passage")
        if run_id is not None:
            try:
                store.finish_run(run_id, status="error", fetched=0, upserted=0, error=str(exc)[:1000])
            except Exception:
                log.exception("Impossible d'enregistrer l'échec dans collector_runs")
        return 1

    if run_id is not None:
        store.finish_run(run_id, status="success", fetched=stats.fetched, upserted=stats.upserted,
                         error=stats.partial_reason)
    log.info("Terminé : %d récupérées, %d enregistrées, %d purgées%s", stats.fetched, stats.upserted,
             stats.purged, f" (partiel : {stats.partial_reason})" if stats.partial_reason else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
