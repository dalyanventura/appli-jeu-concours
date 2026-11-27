import logging
from datetime import datetime, timedelta, timezone

import pytest

from collector.instagram import InstagramError, PermissionDeniedError, RateLimitedError, TokenError
from collector.main import QuotaGuardError, RedactingFormatter, check_hashtag_quota, collect

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


class FakeIG:
    def __init__(self, media_by_tag, fail_on=None, media_by_account=None, account_errors=None):
        self.media_by_tag = media_by_tag
        self.fail_on = fail_on
        self.media_by_account = media_by_account or {}
        self.account_errors = account_errors or {}
        self.searched, self.since, self.discovered = [], {}, []
        self.near_limit, self.usage = False, 0.0

    def discover_media(self, username):
        self.discovered.append(username)
        if username in self.account_errors:
            raise self.account_errors[username]
        return self.media_by_account.get(username, [])

    def search_hashtag(self, tag):
        self.searched.append(tag)
        return f"h_{tag}"

    def iter_recent_media(self, hashtag_id, *, since, max_pages):
        tag = hashtag_id.removeprefix("h_")
        self.since[tag] = since
        if tag == self.fail_on:
            raise RateLimitedError("80002")
        yield from self.media_by_tag.get(tag, [])


class FakeStore:
    def __init__(self, known=None, existing=None, accounts=None):
        self.known = known or {}
        self.existing = existing or []
        self.accounts = accounts or []
        self.dismissed = set()
        self.unchecked = []
        self.writes = []

    def list_account_usernames(self):
        return {a["username"] for a in self.accounts} | self.dismissed

    def save_suggestions(self, mentions, when):
        self.writes.append(("save_suggestions", mentions))
        return len(mentions)

    def list_unchecked_suggestions(self, limit):
        return list(self.unchecked)[:limit]

    def mark_suggestion(self, username, when, *, is_business, recent_contests=None):
        self.writes.append(("mark_suggestion", username, is_business, recent_contests))

    def list_accounts(self, limit):
        return self.accounts[:limit]

    def mark_account(self, username, when, error=None):
        self.writes.append(("mark_account", username, error))

    def list_hashtags(self):
        return self.known

    def save_hashtag_id(self, tag, hashtag_id):
        self.writes.append(("save_hashtag_id", tag, hashtag_id))

    def mark_collected(self, tag, when):
        self.writes.append(("mark_collected", tag))

    def find_existing(self, ids, hashes):
        return self.existing

    def upsert_posts(self, rows):
        self.writes.append(("upsert_posts", rows))
        return len(rows)

    def purge_old_posts(self):
        self.writes.append(("purge",))
        return 0


def iso(delta: timedelta) -> str:
    return (NOW - delta).isoformat()


def test_quota_guard_counts_recent_tags_outside_the_list():
    known = {f"old{i}": {"last_collected_at": iso(timedelta(days=2))} for i in range(25)}
    with pytest.raises(QuotaGuardError):
        check_hashtag_quota(tuple(f"new{i}" for i in range(6)), known, NOW)


def test_quota_guard_ignores_tags_older_than_a_week():
    known = {f"old{i}": {"last_collected_at": iso(timedelta(days=8))} for i in range(25)}
    assert check_hashtag_quota(tuple(f"new{i}" for i in range(20)), known, NOW) == 20


def test_quota_guard_blocks_before_any_api_call():
    known = {f"old{i}": {"last_collected_at": iso(timedelta(hours=3))} for i in range(30)}
    ig = FakeIG({})
    with pytest.raises(QuotaGuardError):
        collect(ig, FakeStore(known), ("jeuconcours",), max_pages=1, now=NOW)
    assert ig.searched == [] and ig.since == {}


def test_run_uses_cached_ids_merges_tags_and_writes(sample_media):
    known = {"jeuconcours": {"tag": "jeuconcours", "ig_hashtag_id": "h_jeuconcours",
                             "last_collected_at": iso(timedelta(minutes=30))}}
    ig = FakeIG({"jeuconcours": sample_media, "concours": sample_media[:1]})
    store = FakeStore(known)

    stats = collect(ig, store, ("jeuconcours", "concours"), max_pages=3, now=NOW)

    assert ig.searched == ["concours"]
    assert ig.since["jeuconcours"] == NOW - timedelta(minutes=90)     # last run - 1 h overlap
    assert ig.since["concours"] == NOW - timedelta(hours=24)
    assert stats.fetched == 8 and stats.upserted == 5
    upserted = next(w[1] for w in store.writes if w[0] == "upsert_posts")
    first = next(r for r in upserted if r["ig_media_id"] == "1001")
    assert first["source_hashtags"] == ["concours", "jeuconcours"]
    assert ("save_hashtag_id", "concours", "h_concours") in store.writes
    assert ("mark_collected", "jeuconcours") in store.writes and ("purge",) in store.writes


def test_dry_run_writes_nothing(sample_media):
    store = FakeStore()
    stats = collect(FakeIG({"jeuconcours": sample_media}), store, ("jeuconcours",),
                    max_pages=1, now=NOW, dry_run=True)
    assert stats.fetched == 7 and store.writes == []


def test_rate_limit_keeps_what_was_already_collected(sample_media):
    store = FakeStore()
    stats = collect(FakeIG({"jeuconcours": sample_media}, fail_on="concours"), store,
                    ("jeuconcours", "concours", "giveawayfrance"), max_pages=1, now=NOW)
    assert "concours" in stats.partial_reason
    assert stats.upserted == 5
    assert ("mark_collected", "concours") not in store.writes
    assert ("mark_collected", "giveawayfrance") not in store.writes


def test_redacting_formatter_hides_secrets_in_tracebacks():
    formatter = RedactingFormatter("%(message)s", ["SECRET_TOKEN"])
    try:
        raise ValueError("url?access_token=SECRET_TOKEN")
    except ValueError:
        record = logging.LogRecord("x", logging.ERROR, "", 0, "boom SECRET_TOKEN", None, None)
        import sys
        record.exc_info = sys.exc_info()
    text = formatter.format(record)
    assert "SECRET_TOKEN" not in text and "***" in text


def account_post(media_id, caption, hours_ago):
    ts = (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%S+0000")
    return {"id": media_id, "caption": caption, "media_type": "IMAGE",
            "permalink": f"https://www.instagram.com/p/{media_id}/", "timestamp": ts}


def upserted_rows(store):
    return {r["ig_media_id"]: r for w in store.writes if w[0] == "upsert_posts" for r in w[1]}


def test_followed_accounts_keep_only_recent_contest_posts():
    ig = FakeIG({}, media_by_account={"marque_exemple": [
        account_post("a1", "🎁 JEU CONCOURS : un sac à gagner !", 2),
        account_post("a2", "Notre nouvelle collection est arrivée", 3),
        account_post("a3", "Giveaway : tirage au sort lundi", 24 * 10),   # older than first lookback
    ]})
    store = FakeStore(accounts=[{"username": "marque_exemple", "last_collected_at": None}])
    stats = collect(ig, store, (), max_pages=1, now=NOW)
    rows = upserted_rows(store)
    assert list(rows) == ["a1"]
    assert rows["a1"]["author_username"] == "marque_exemple"
    assert rows["a1"]["source_hashtags"] == []
    assert stats.fetched == 2
    assert ("mark_account", "marque_exemple", None) in store.writes


def test_same_post_from_hashtag_and_account_gets_author(sample_media):
    first = sample_media[0]
    ig = FakeIG({"jeuconcours": [first]}, media_by_account={"boulangerie_exemple": [first]})
    store = FakeStore(accounts=[{"username": "boulangerie_exemple",
                                 "last_collected_at": (NOW - timedelta(days=30)).isoformat()}])
    collect(ig, store, ("jeuconcours",), max_pages=1, now=NOW)
    row = upserted_rows(store)["1001"]
    assert row["author_username"] == "boulangerie_exemple"
    assert row["source_hashtags"] == ["jeuconcours"]


def test_non_business_account_is_recorded_and_skipped():
    ig = FakeIG({}, media_by_account={"ok_compte": [account_post("b1", "Concours !", 1)]},
                account_errors={"perso": InstagramError("code 110 — not a business account")})
    store = FakeStore(accounts=[{"username": "perso"}, {"username": "ok_compte"}])
    collect(ig, store, (), max_pages=1, now=NOW)
    assert ig.discovered == ["perso", "ok_compte"]
    assert any(w[:2] == ("mark_account", "perso") and "110" in w[2] for w in store.writes)
    assert "b1" in upserted_rows(store)


def test_token_error_on_account_fails_the_run():
    ig = FakeIG({}, account_errors={"x": TokenError("expired")})
    with pytest.raises(TokenError):
        collect(ig, FakeStore(accounts=[{"username": "x"}]), (), max_pages=1, now=NOW)


def test_accounts_are_limited_per_run():
    store = FakeStore(accounts=[{"username": f"c{i}"} for i in range(5)])
    ig = FakeIG({})
    collect(ig, store, (), max_pages=1, now=NOW, max_accounts=2)
    assert ig.discovered == ["c0", "c1"]


def test_accounts_skipped_when_hashtags_hit_rate_limit():
    ig = FakeIG({}, fail_on="jeuconcours")
    collect(ig, FakeStore(accounts=[{"username": "c0"}]), ("jeuconcours",), max_pages=1, now=NOW)
    assert ig.discovered == []


def test_partner_brands_are_suggested_once_unless_already_followed():
    ig = FakeIG({}, media_by_account={
        "marque_a": [account_post("p1", "Concours avec @marque_b et @nouvelle_marque !", 1)],
        "marque_b": [account_post("p2", "Giveaway x @nouvelle_marque x @refusee", 1),
                     account_post("p3", "Nouvelle collection avec @studio_mode", 1)],
    })
    store = FakeStore(accounts=[{"username": "marque_a"}, {"username": "marque_b"}])
    store.dismissed = {"refusee"}
    collect(ig, store, (), max_pages=1, now=NOW)
    saved = next(w[1] for w in store.writes if w[0] == "save_suggestions")
    assert saved == {"nouvelle_marque": {"marque_a", "marque_b"}}


def test_dry_run_does_not_save_suggestions():
    ig = FakeIG({}, media_by_account={"marque_a": [account_post("p1", "Concours avec @x_y", 1)]})
    store = FakeStore(accounts=[{"username": "marque_a"}])
    collect(ig, store, (), max_pages=1, now=NOW, dry_run=True)
    assert store.writes == []


def test_missing_permission_stops_accounts_without_blaming_them(sample_media):
    ig = FakeIG({"jeuconcours": sample_media},
                account_errors={"a": PermissionDeniedError("code 10"), "b": PermissionDeniedError("code 10")})
    store = FakeStore(accounts=[{"username": "a"}, {"username": "b"}])
    stats = collect(ig, store, ("jeuconcours",), max_pages=1, now=NOW)
    assert ig.discovered == ["a"]
    assert not any(w[0] == "mark_account" for w in store.writes)
    assert "permission" in stats.partial_reason and stats.upserted == 5


def test_collected_rows_carry_classification(sample_media):
    store = FakeStore()
    collect(FakeIG({"jeuconcours": sample_media}), store, ("jeuconcours",), max_pages=1, now=NOW)
    for row in upserted_rows(store).values():
        assert {"contest_score", "entry_type", "categories", "deadline"} <= set(row)
        assert "is_hidden" not in row


def test_partner_suggestions_are_checked_with_business_discovery():
    ig = FakeIG({}, media_by_account={"vraie_marque": [account_post("v1", "Concours : un lot à gagner", 24)]},
                account_errors={"mot_courant": InstagramError("code 110")})
    store = FakeStore()
    store.unchecked = ["vraie_marque", "mot_courant"]
    collect(ig, store, (), max_pages=1, now=NOW)
    assert ("mark_suggestion", "vraie_marque", True, 1) in store.writes
    assert ("mark_suggestion", "mot_courant", False, None) in store.writes


def test_suggestion_checks_stop_on_missing_permission():
    ig = FakeIG({}, account_errors={"a": PermissionDeniedError("code 10")})
    store = FakeStore()
    store.unchecked = ["a", "b"]
    collect(ig, store, (), max_pages=1, now=NOW)
    assert ig.discovered == ["a"] and not any(w[0] == "mark_suggestion" for w in store.writes)
