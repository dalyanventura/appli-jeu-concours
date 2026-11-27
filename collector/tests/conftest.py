import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_media() -> list[dict]:
    return json.loads((FIXTURES / "recent_media_sample.json").read_text(encoding="utf-8"))["data"]
