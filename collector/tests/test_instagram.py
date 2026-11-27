import json
from datetime import datetime, timezone

import httpx
import pytest

from collector.instagram import (InstagramClient, InstagramError, PermissionDeniedError, RateLimitedError,
                                 usage_percent)

TOKEN = "SECRET_TOKEN_123"


def make_client(handler, **kwargs) -> InstagramClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return InstagramClient(TOKEN, "42", "v27.0", http=http, sleep=lambda _: None, **kwargs)


def media(media_id: str, ts: str) -> dict:
    return {"id": media_id, "timestamp": ts, "media_type": "IMAGE", "permalink": f"https://x/{media_id}"}


def page(items, after=None, headers=None):
    paging = {"cursors": {"after": after}, "next": "https://graph.facebook.com/...&access_token=x"} if after else {}
    return httpx.Response(200, json={"data": items, "paging": paging}, headers=headers or {})


SINCE = datetime(2026, 11, 27, 10, 0, tzinfo=timezone.utc)


def paginated_handler(requests):
    pages = {
        None: page([media("1", "2026-11-27T11:00:00+0000"), media("2", "2026-11-27T10:50:00+0000")], "c1"),
        "c1": page([media("3", "2026-11-27T10:40:00+0000"), media("4", "2026-11-27T09:00:00+0000")], "c2"),
        "c2": page([media("5", "2026-11-27T08:00:00+0000")]),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return pages[request.url.params.get("after")]
    return handler


def test_discover_media_builds_nested_fields_and_parses_media():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"business_discovery": {"username": "marque", "id": "9",
                              "media": {"data": [media("m1", "2026-11-27T11:00:00+0000")]}}, "id": "42"})
    client = make_client(handler)
    assert [m["id"] for m in client.discover_media("marque")] == ["m1"]
    assert seen[0].url.path == "/v27.0/42"
    assert seen[0].url.params["fields"].startswith(
        "business_discovery.username(marque){username,media.limit(25){id,")


@pytest.mark.parametrize("username", ["@marque", "Marque", "a b", "x){y", ""])
def test_discover_media_rejects_invalid_usernames(username):
    client = make_client(lambda r: pytest.fail("no request expected"))
    with pytest.raises(ValueError):
        client.discover_media(username)


def test_search_hashtag_returns_first_id():
    client = make_client(lambda r: httpx.Response(200, json={"data": [{"id": "h1"}]}))
    assert client.search_hashtag("jeuconcours") == "h1"


def test_search_hashtag_unknown_returns_none():
    client = make_client(lambda r: httpx.Response(200, json={"data": []}))
    assert client.search_hashtag("nope") is None


def test_pagination_stops_once_a_page_reaches_since():
    requests = []
    client = make_client(paginated_handler(requests))
    items = list(client.iter_recent_media("h1", since=SINCE, max_pages=5))
    assert [i["id"] for i in items] == ["1", "2", "3", "4"]
    assert len(requests) == 2
    assert requests[1].url.params["after"] == "c1"


def test_pagination_respects_max_pages():
    requests = []
    client = make_client(paginated_handler(requests))
    list(client.iter_recent_media("h1", since=datetime(2000, 1, 1, tzinfo=timezone.utc), max_pages=1))
    assert len(requests) == 1


def test_pagination_stops_without_next_page():
    requests = []
    client = make_client(paginated_handler(requests))
    items = list(client.iter_recent_media("h1", since=datetime(2000, 1, 1, tzinfo=timezone.utc), max_pages=10))
    assert len(items) == 5 and len(requests) == 3


def test_high_usage_header_stops_pagination():
    requests = []

    def handler(request):
        requests.append(request)
        return page([media("1", "2026-11-27T11:00:00+0000")], "c1",
                    headers={"x-app-usage": json.dumps({"call_count": 85, "total_time": 3, "total_cputime": 2})})
    client = make_client(handler)
    list(client.iter_recent_media("h1", since=SINCE, max_pages=5))
    assert len(requests) == 1 and client.near_limit


def test_business_usage_header_is_parsed():
    headers = httpx.Headers({"x-business-use-case-usage": json.dumps(
        {"1784": [{"type": "instagram", "call_count": 12, "total_cputime": 91, "total_time": 4}]})})
    assert usage_percent(headers) == 91


def test_expired_token_error_does_not_leak_token():
    client = make_client(lambda r: httpx.Response(400, json={"error": {
        "code": 190, "message": "Error validating access token", "type": "OAuthException"}}))
    with pytest.raises(InstagramError) as excinfo:
        client.search_hashtag("x")
    assert "expiré" in str(excinfo.value)
    assert TOKEN not in str(excinfo.value)


def test_rate_limit_error_code():
    client = make_client(lambda r: httpx.Response(400, json={"error": {"code": 80002, "message": "too many"}}))
    with pytest.raises(RateLimitedError):
        client.search_hashtag("x")


def test_server_error_is_retried():
    responses = iter([httpx.Response(500, json={}), httpx.Response(200, json={"data": [{"id": "h9"}]})])
    client = make_client(lambda r: next(responses))
    assert client.search_hashtag("x") == "h9"


def test_network_error_message_has_no_token():
    def handler(request):
        raise httpx.ConnectError(f"failed {request.url}")
    client = make_client(handler)
    with pytest.raises(InstagramError) as excinfo:
        client.search_hashtag("x")
    assert TOKEN not in str(excinfo.value)
    assert excinfo.value.__cause__ is None


def test_permission_error_code_10():
    client = make_client(lambda r: httpx.Response(400, json={"error": {
        "code": 10, "message": "(#10) Application does not have permission for this action"}}))
    with pytest.raises(PermissionDeniedError):
        client.discover_media("marque")
