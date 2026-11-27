"""Themes of a contest, from keywords in collector/config/categories.yaml."""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

import yaml

from collector.config import CONFIG_DIR, ConfigError
from collector.normalize import fold

FALLBACK = "autre"
MAX_CATEGORIES = 3
# "#concoursbeaute" / "#jeuconcoursmode" → "beaute" / "mode", so theme words inside hashtags count
CONTEST_PREFIX = re.compile(r"#?(?:jeux?)?concours(?=[a-z])")


@lru_cache(maxsize=4)
def load_categories(path: Path = CONFIG_DIR / "categories.yaml") -> dict[str, list[re.Pattern]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = data.get("categories") or {}
    if not raw or not all(isinstance(v, list) and v for v in raw.values()):
        raise ConfigError(f"{path.name} : chaque thème doit avoir une liste de mots-clés")
    if FALLBACK in raw:
        raise ConfigError(f"{path.name} : « {FALLBACK} » est implicite, ne pas le lister")
    try:
        return {slug: [re.compile(rf"(?<![a-z0-9]){kw}") for kw in keywords] for slug, keywords in raw.items()}
    except re.error as exc:
        raise ConfigError(f"{path.name} : mot-clé invalide ({exc})") from None


def classify(caption: str | None, source_hashtags: Iterable[str] = ()) -> list[str]:
    """Up to 3 themes, most keyword hits first (ties: order of the YAML file); else ["autre"]."""
    text = " ".join([fold(caption), *(fold(t) for t in source_hashtags)])
    text = CONTEST_PREFIX.sub(" ", text)
    order = {slug: i for i, slug in enumerate(load_categories())}
    hits = {slug: sum(1 for rx in patterns if rx.search(text)) for slug, patterns in load_categories().items()}
    ranked = sorted((slug for slug, n in hits.items() if n), key=lambda s: (-hits[s], order[s]))
    return ranked[:MAX_CATEGORIES] or [FALLBACK]
