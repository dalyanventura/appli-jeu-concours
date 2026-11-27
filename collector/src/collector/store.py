"""Supabase access through its REST API (PostgREST), with the secret key (bypasses RLS)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timezone

import httpx

LOOKUP_CHUNK = 50     # values per `in.(...)` filter, keeps URLs short
UPSERT_CHUNK = 500


class StoreError(RuntimeError):
    pass


def _chunks(values: Sequence, size: int) -> Iterable[Sequence]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


class SupabaseStore:
    def __init__(self, url: str, secret_key: str, *, transport: httpx.BaseTransport | None = None) -> None:
        headers = {"apikey": secret_key, "Content-Type": "application/json"}
        if secret_key.startswith("eyJ"):   # legacy service_role JWT
            headers["Authorization"] = f"Bearer {secret_key}"
        self._http = httpx.Client(base_url=f"{url.rstrip('/')}/rest/v1/", headers=headers,
                                  timeout=30, transport=transport)

    def _request(self, method: str, path: str, *, params: dict | None = None,
                 json: object | None = None, prefer: str | None = None) -> object:
        headers = {"Prefer": prefer} if prefer else None
        resp = self._http.request(method, path, params=params, json=json, headers=headers)
        if resp.status_code >= 400:
            raise StoreError(f"{method} {path}: HTTP {resp.status_code} — {resp.text[:300]}")
        return resp.json() if resp.content else None

    # -- hashtags ------------------------------------------------------------
    def list_hashtags(self) -> dict[str, dict]:
        rows = self._request("GET", "hashtags", params={"select": "tag,ig_hashtag_id,last_collected_at"})
        return {row["tag"]: row for row in rows or []}

    def _upsert_hashtag(self, row: dict) -> None:
        self._request("POST", "hashtags", params={"on_conflict": "tag"}, json=[row],
                      prefer="resolution=merge-duplicates,return=minimal")

    def save_hashtag_id(self, tag: str, hashtag_id: str) -> None:
        self._upsert_hashtag({"tag": tag, "ig_hashtag_id": hashtag_id})

    def mark_collected(self, tag: str, when: datetime) -> None:
        self._upsert_hashtag({"tag": tag, "last_collected_at": when.isoformat()})

    # -- posts ---------------------------------------------------------------
    def find_existing(self, media_ids: Sequence[str], hashes: Sequence[str]) -> list[dict]:
        """Stored posts sharing an ig_media_id or a caption_hash with the batch."""
        found: dict[str, dict] = {}
        for column, values in (("ig_media_id", list(media_ids)), ("caption_hash", list(hashes))):
            for chunk in _chunks(values, LOOKUP_CHUNK):
                rows = self._request("GET", "posts", params={
                    "select": "ig_media_id,caption_hash,source_hashtags",
                    column: f"in.({','.join(chunk)})",
                })
                for row in rows or []:
                    found[row["ig_media_id"]] = row
        return list(found.values())

    def upsert_posts(self, rows: Sequence[dict]) -> int:
        """Insert or update collection columns only; classification/moderation columns are untouched.

        Rows are sent in groups sharing the same keys: PostgREST applies one column list per
        request, and a row without `author_username` must not overwrite a known author with NULL.
        """
        groups: dict[frozenset, list[dict]] = {}
        for row in rows:
            groups.setdefault(frozenset(row), []).append(row)
        for group in groups.values():
            for chunk in _chunks(group, UPSERT_CHUNK):
                self._request("POST", "posts", params={"on_conflict": "ig_media_id"}, json=list(chunk),
                              prefer="resolution=merge-duplicates,return=minimal")
        return len(rows)

    # -- followed accounts ---------------------------------------------------
    def list_accounts(self, limit: int) -> list[dict]:
        """Enabled accounts, least recently collected first (rotation when there are many)."""
        return self._request("GET", "accounts", params={
            "select": "username,last_collected_at",
            "enabled": "is.true",
            "order": "last_collected_at.asc.nullsfirst",
            "limit": str(limit),
        }) or []

    def mark_account(self, username: str, when: datetime, error: str | None = None) -> None:
        """Success: advance last_collected_at and clear the error. Failure: only record the error,
        so a later successful read still gets its full first lookback."""
        body = {"last_error": error} if error else {"last_collected_at": when.isoformat(), "last_error": None}
        self._request("PATCH", "accounts", params={"username": f"eq.{username}"}, json=body,
                      prefer="return=minimal")

    def list_account_usernames(self) -> set[str]:
        """Every account in `accounts`, enabled or not (disabled = suggestion dismissed)."""
        rows = self._request("GET", "accounts", params={"select": "username"}) or []
        return {row["username"] for row in rows}

    def save_suggestions(self, mentions: dict[str, set[str]], when: datetime) -> int:
        """Upsert partner brands into `account_suggestions`, merging who mentioned them."""
        names = sorted(mentions)
        stored: dict[str, set[str]] = {}
        for chunk in _chunks(names, LOOKUP_CHUNK):
            rows = self._request("GET", "account_suggestions", params={
                "select": "username,mentioned_by", "username": f"in.({','.join(chunk)})"})
            for row in rows or []:
                stored[row["username"]] = set(row.get("mentioned_by") or [])
        payload = []
        for name in names:
            by = sorted(mentions[name] | stored.get(name, set()))
            payload.append({"username": name, "mentioned_by": by, "mention_count": len(by),
                            "last_seen_at": when.isoformat()})
        for chunk in _chunks(payload, UPSERT_CHUNK):
            self._request("POST", "account_suggestions", params={"on_conflict": "username"},
                          json=list(chunk), prefer="resolution=merge-duplicates,return=minimal")
        return len(payload)

    def list_unchecked_suggestions(self, limit: int) -> list[str]:
        rows = self._request("GET", "account_suggestions", params={
            "select": "username", "is_business": "is.null",
            "order": "mention_count.desc,last_seen_at.desc", "limit": str(limit)}) or []
        return [row["username"] for row in rows]

    def mark_suggestion(self, username: str, when: datetime, *, is_business: bool,
                        recent_contests: int | None = None) -> None:
        self._request("PATCH", "account_suggestions", params={"username": f"eq.{username}"}, json={
            "checked_at": when.isoformat(), "is_business": is_business, "recent_contests": recent_contests,
        }, prefer="return=minimal")

    def iter_posts(self, columns: str, page_size: int = 1000):
        """Every stored post, page by page (for reclassification)."""
        offset = 0
        while True:
            rows = self._request("GET", "posts", params={
                "select": columns, "order": "ig_media_id", "limit": str(page_size), "offset": str(offset)}) or []
            yield from rows
            if len(rows) < page_size:
                return
            offset += page_size

    def purge_old_posts(self) -> int:
        return int(self._request("POST", "rpc/purge_old_posts", json={}) or 0)

    # -- runs ----------------------------------------------------------------
    def start_run(self) -> int:
        rows = self._request("POST", "collector_runs", json={"status": "running"},
                             prefer="return=representation")
        return rows[0]["id"]

    def finish_run(self, run_id: int, *, status: str, fetched: int, upserted: int,
                   error: str | None = None) -> None:
        self._request("PATCH", "collector_runs", params={"id": f"eq.{run_id}"}, json={
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "posts_fetched": fetched,
            "posts_upserted": upserted,
            "error": error,
        }, prefer="return=minimal")
