from datetime import datetime, timedelta, timezone

import httpx

from collector.ig_token import REQUIRED_SCOPES, check, replace_env_value

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
TOKEN = "SECRET_TOKEN_123"


def debug_client(**data):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"data": {"is_valid": True, "scopes": sorted(REQUIRED_SCOPES), **data}})
    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def ts(days: float) -> int:
    return int((NOW + timedelta(days=days)).timestamp())


def test_healthy_token():
    http, seen = debug_client(expires_at=ts(50), data_access_expires_at=ts(80))
    code, message = check(TOKEN, "v27.0", NOW, http=http)
    assert code == 0 and "50 jours" in message
    assert seen[0].url.params["input_token"] == TOKEN and seen[0].url.path == "/v27.0/debug_token"


def test_earliest_deadline_wins_and_warns():
    http, _ = debug_client(expires_at=ts(50), data_access_expires_at=ts(10))
    code, message = check(TOKEN, "v27.0", NOW, http=http)
    assert code == 0 and "bientôt" in message and "accès aux données" in message


def test_close_deadline_fails():
    http, _ = debug_client(expires_at=ts(3), data_access_expires_at=0)
    code, message = check(TOKEN, "v27.0", NOW, http=http)
    assert code == 1 and "MAINTENANT" in message and TOKEN not in message


def test_never_expiring_token():
    http, _ = debug_client(expires_at=0, data_access_expires_at=0)
    assert check(TOKEN, "v27.0", NOW, http=http)[0] == 0


def test_invalid_or_missing_scope_fails():
    http, _ = debug_client(is_valid=False)
    assert check(TOKEN, "v27.0", NOW, http=http)[0] == 1
    http, _ = debug_client(scopes=["instagram_basic"], expires_at=ts(50))
    code, message = check(TOKEN, "v27.0", NOW, http=http)
    assert code == 1 and "instagram_manage_insights" in message


def test_replace_env_value_keeps_other_lines():
    text = "# comment\nIG_ACCESS_TOKEN=old\nIG_USER_ID=42\n"
    assert replace_env_value(text, "IG_ACCESS_TOKEN", "new") == "# comment\nIG_ACCESS_TOKEN=new\nIG_USER_ID=42\n"
    assert replace_env_value("A=1\n", "B", "2") == "A=1\nB=2\n"
