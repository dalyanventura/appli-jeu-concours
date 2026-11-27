"""Settings (environment / .env) and hashtag list (config/hashtags.yaml)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parents[3]          # repository root (editable install)
CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
WEEKLY_HASHTAG_LIMIT = 30


class ConfigError(ValueError):
    pass


def load_dotenv(path: Path = ROOT_DIR / ".env") -> None:
    """Minimal .env loader; real environment variables (e.g. GitHub secrets) take precedence."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    ig_access_token: str
    ig_user_id: str
    graph_api_version: str
    supabase_url: str
    supabase_secret_key: str

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        required = ("IG_ACCESS_TOKEN", "IG_USER_ID", "SUPABASE_URL", "SUPABASE_SECRET_KEY")
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise ConfigError(f"Variables d'environnement manquantes : {', '.join(missing)}")
        return cls(
            ig_access_token=os.environ["IG_ACCESS_TOKEN"],
            ig_user_id=os.environ["IG_USER_ID"],
            graph_api_version=os.environ.get("GRAPH_API_VERSION", "v27.0"),
            supabase_url=os.environ["SUPABASE_URL"],
            supabase_secret_key=os.environ["SUPABASE_SECRET_KEY"],
        )


@dataclass(frozen=True)
class HashtagConfig:
    tags: tuple[str, ...]
    max_pages_per_tag: int


def load_hashtag_config(path: Path = CONFIG_DIR / "hashtags.yaml") -> HashtagConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    tags = data.get("hashtags") or []
    max_pages = data.get("max_pages_per_tag", 3)

    for tag in tags:
        if not isinstance(tag, str) or not tag or tag != tag.lower() or tag.startswith("#") \
                or any(ch.isspace() for ch in tag):
            raise ConfigError(f"Hashtag invalide dans {path.name} : {tag!r} (minuscules, sans '#', sans espace)")
    duplicates = sorted({t for t in tags if tags.count(t) > 1})
    if duplicates:
        raise ConfigError(f"Hashtags en double dans {path.name} : {', '.join(duplicates)}")
    if len(tags) > WEEKLY_HASHTAG_LIMIT:
        raise ConfigError(f"{len(tags)} hashtags dans {path.name} : maximum {WEEKLY_HASHTAG_LIMIT}")
    if not isinstance(max_pages, int) or not 1 <= max_pages <= 10:
        raise ConfigError("max_pages_per_tag doit être un entier entre 1 et 10")
    return HashtagConfig(tags=tuple(tags), max_pages_per_tag=max_pages)
