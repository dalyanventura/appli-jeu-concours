"""Instagram Graph API client (Facebook Login flavour) for hashtag search.

The access token travels as a query parameter, so request URLs must never be logged:
error messages are built from the API's JSON error only, and pagination uses the
`after` cursor rather than the `paging.next` URL (which embeds the token).
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Iterator
from datetime import datetime

import httpx

log = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com"
MEDIA_FIELDS = "id,caption,media_type,media_url,permalink,timestamp"
PAGE_SIZE = 50
RATE_LIMIT_CODES = {4, 17, 32, 613, 80002}
TOKEN_ERROR_CODE = 190
PERMISSION_CODES = {10, *range(200, 300)}   # permission missing on the token / app


class InstagramError(RuntimeError):
    pass


class RateLimitedError(InstagramError):
    pass


class PermissionDeniedError(InstagramError):
    """The token or the app lacks a permission: every similar call will fail the same way."""


class TokenError(InstagramError):
    pass


USERNAME_RE = re.compile(r"[a-z0-9._]{1,30}")
DISCOVERY_PAGE_SIZE = 25


def parse_timestamp(value: str) -> datetime:
    """Graph API timestamps look like 2026-11-27T11:23:16+0000."""
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")


def usage_percent(headers: httpx.Headers) -> float:
    """Highest usage percentage reported by X-App-Usage / X-Business-Use-Case-Usage."""
    buckets: list[dict] = []
    try:
        if raw := headers.get("x-app-usage"):
            buckets.append(json.loads(raw))
        if raw := headers.get("x-business-use-case-usage"):
            for entries in json.loads(raw).values():
                buckets.extend(entries)
    except (ValueError, AttributeError, TypeError):
        log.warning("En-tête de quota illisible, ignoré")
    highest = 0.0
    for bucket in buckets:
        for key in ("call_count", "total_cputime", "total_time"):
            value = bucket.get(key) if isinstance(bucket, dict) else None
            if isinstance(value, (int, float)):
                highest = max(highest, float(value))
    return highest


class InstagramClient:
    def __init__(
        self,
        access_token: str,
        ig_user_id: str,
        api_version: str,
        *,
        http: httpx.Client | None = None,
        usage_threshold: float = 80.0,
        max_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._token = access_token
        self._user_id = ig_user_id
        self._version = api_version
        self._http = http or httpx.Client(timeout=30)
        self._threshold = usage_threshold
        self._max_attempts = max_attempts
        self._sleep = sleep
        self.usage = 0.0

    @property
    def near_limit(self) -> bool:
        return self.usage >= self._threshold

    def _get(self, path: str, params: dict[str, str]) -> dict:
        url = f"{GRAPH_URL}/{self._version}/{path}"
        query = {**params, "access_token": self._token}
        for attempt in range(1, self._max_attempts + 1):
            try:
                resp = self._http.get(url, params=query)
            except httpx.TransportError as exc:
                if attempt == self._max_attempts:
                    raise InstagramError(f"{path}: erreur réseau ({type(exc).__name__})") from None
                self._sleep(2 ** attempt)
                continue
            self.usage = max(self.usage, usage_percent(resp.headers))
            if resp.status_code >= 500 and attempt < self._max_attempts:
                self._sleep(2 ** attempt)
                continue
            break

        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code == 200:
            return data

        err = data.get("error", {}) if isinstance(data, dict) else {}
        code = err.get("code")
        message = (f"{path}: HTTP {resp.status_code}, code {code}/{err.get('error_subcode')} — "
                   f"{err.get('message', 'réponse illisible')}")
        if code in RATE_LIMIT_CODES:
            raise RateLimitedError(message)
        if code == TOKEN_ERROR_CODE:
            raise TokenError(f"Token Instagram invalide ou expiré. {message}")
        if code in PERMISSION_CODES:
            raise PermissionDeniedError(message)
        raise InstagramError(message)

    def search_hashtag(self, tag: str) -> str | None:
        """Hashtag name → ID. Counts against the 30-unique-hashtags / 7-day quota."""
        data = self._get("ig_hashtag_search", {"user_id": self._user_id, "q": tag})
        items = data.get("data") or []
        return items[0]["id"] if items else None

    def discover_media(self, username: str) -> list[dict]:
        """Latest posts of another Business/Creator account (Business Discovery).

        Does not count against the hashtag quota, but does against the platform rate limit
        (one call per account). Personal accounts and age-gated accounts raise InstagramError.
        """
        if not USERNAME_RE.fullmatch(username):
            raise ValueError(f"Nom de compte invalide : {username!r}")
        fields = (f"business_discovery.username({username})"
                  f"{{username,media.limit({DISCOVERY_PAGE_SIZE}){{{MEDIA_FIELDS}}}}}")
        data = self._get(self._user_id, {"fields": fields})
        discovery = data.get("business_discovery") or {}
        return (discovery.get("media") or {}).get("data") or []

    def iter_recent_media(self, hashtag_id: str, *, since: datetime, max_pages: int) -> Iterator[dict]:
        """Yield media from the last 24 h, newest first, until a page reaches `since`."""
        after: str | None = None
        for _ in range(max_pages):
            if self.near_limit:
                log.warning("Quota API à %.0f %% : arrêt de la pagination", self.usage)
                return
            params = {"user_id": self._user_id, "fields": MEDIA_FIELDS, "limit": str(PAGE_SIZE)}
            if after:
                params["after"] = after
            data = self._get(f"{hashtag_id}/recent_media", params)
            items = data.get("data") or []
            yield from items
            if not items:
                return
            timestamps = [parse_timestamp(i["timestamp"]) for i in items if i.get("timestamp")]
            paging = data.get("paging") or {}
            after = (paging.get("cursors") or {}).get("after")
            if (timestamps and min(timestamps) < since) or not after or "next" not in paging:
                return
