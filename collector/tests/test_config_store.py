import json

import httpx
import pytest

from collector.config import ConfigError, load_hashtag_config
from collector.store import SupabaseStore


def write_config(tmp_path, body: str):
    path = tmp_path / "hashtags.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_real_hashtag_config_is_valid():
    config = load_hashtag_config()
    assert 0 < len(config.tags) <= 30


@pytest.mark.parametrize("body", [
    "hashtags: ['#concours']",
    "hashtags: [Concours]",
    "hashtags: ['jeu concours']",
    "hashtags: [concours, concours]",
    "hashtags: [" + ", ".join(f"t{i}" for i in range(31)) + "]",
    "max_pages_per_tag: 0\nhashtags: [concours]",
])
def test_invalid_hashtag_configs_are_rejected(tmp_path, body):
    with pytest.raises(ConfigError):
        load_hashtag_config(write_config(tmp_path, body))


def recording_store(responses=None):
    requests = []

    def handler(request):
        requests.append(request)
        return (responses or {}).get(request.url.path, httpx.Response(200, json=[]))
    store = SupabaseStore("https://proj.supabase.co", "sb_secret_x",
                          transport=httpx.MockTransport(handler))
    return store, requests


def test_upsert_targets_ig_media_id_and_merges():
    store, requests = recording_store()
    store.upsert_posts([{"ig_media_id": str(i)} for i in range(501)])
    assert len(requests) == 2
    req = requests[0]
    assert req.url.path == "/rest/v1/posts" and req.url.params["on_conflict"] == "ig_media_id"
    assert "resolution=merge-duplicates" in req.headers["prefer"]
    assert req.headers["apikey"] == "sb_secret_x" and "authorization" not in req.headers
    assert len(json.loads(req.content)) == 500


def test_upsert_groups_rows_by_columns_so_author_is_never_nulled():
    store, requests = recording_store()
    store.upsert_posts([{"ig_media_id": "1"}, {"ig_media_id": "2", "author_username": "a"},
                        {"ig_media_id": "3"}])
    bodies = sorted((json.loads(r.content) for r in requests), key=len)
    assert bodies == [[{"ig_media_id": "2", "author_username": "a"}],
                      [{"ig_media_id": "1"}, {"ig_media_id": "3"}]]


def test_list_accounts_orders_never_collected_first():
    store, requests = recording_store()
    store.list_accounts(60)
    params = requests[0].url.params
    assert params["order"] == "last_collected_at.asc.nullsfirst" and params["limit"] == "60"
    assert params["enabled"] == "is.true"


def test_find_existing_chunks_lookups():
    store, requests = recording_store()
    store.find_existing([str(i) for i in range(120)], ["a", "b"])
    assert len(requests) == 4   # 3 chunks of ids + 1 of hashes
    assert requests[0].url.params["ig_media_id"].startswith("in.(0,1,")


def test_store_errors_are_raised():
    store, _ = recording_store({"/rest/v1/hashtags": httpx.Response(401, json={"message": "bad key"})})
    with pytest.raises(Exception, match="401"):
        store.list_hashtags()


def test_save_suggestions_merges_with_stored_mentions():
    from datetime import datetime, timezone
    store, requests = recording_store({"/rest/v1/account_suggestions": httpx.Response(
        200, json=[{"username": "b", "mentioned_by": ["old"]}])})
    store.save_suggestions({"b": {"new"}, "c": {"new"}}, datetime(2026, 11, 27, tzinfo=timezone.utc))
    post = next(r for r in requests if r.method == "POST")
    assert post.url.params["on_conflict"] == "username"
    body = {row["username"]: row for row in json.loads(post.content)}
    assert body["b"]["mentioned_by"] == ["new", "old"] and body["b"]["mention_count"] == 2
    assert body["c"]["mention_count"] == 1 and "first_seen_at" not in body["c"]


def test_failed_account_read_does_not_advance_last_collected_at():
    from datetime import datetime, timezone
    store, requests = recording_store()
    when = datetime(2026, 11, 27, tzinfo=timezone.utc)
    store.mark_account("perso", when, error="code 110")
    store.mark_account("marque", when)
    assert json.loads(requests[0].content) == {"last_error": "code 110"}
    assert json.loads(requests[1].content) == {"last_collected_at": when.isoformat(), "last_error": None}


def test_reclassify_sends_back_not_null_columns_and_analysis():
    from collector.reclassify import reclassify
    post = {"ig_media_id": "1", "permalink": "p", "caption": "JEU CONCOURS : like + abonne-toi, tirage le 07/12",
            "caption_hash": "h", "media_type": "IMAGE", "published_at": "2026-11-27T10:00:00+00:00",
            "source_hashtags": ["jeuconcours"]}
    store, requests = recording_store({"/rest/v1/posts": httpx.Response(200, json=[post])})
    stats = reclassify(store, dry_run=False)
    assert stats["posts"] == 1 and stats["affichés"] == 1
    sent = json.loads(next(r for r in requests if r.method == "POST").content)[0]
    assert sent["caption_hash"] == "h" and sent["deadline"] == "2026-12-07" and "is_hidden" not in sent
