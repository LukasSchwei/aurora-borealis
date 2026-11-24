"""Persistent application configuration for Aurora Borealis."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .paths import get_default_characters_dir


def default_characters_dir() -> str:
    return str(get_default_characters_dir())


@dataclass
class AppConfig:
    characters_dir: str = field(default_factory=default_characters_dir)
    custom_dirs: list[str] = field(default_factory=list)
    installed_indexes: list[dict] = field(default_factory=list)
    favorites: list[str] = field(default_factory=list)
    auto_imported_official: bool = False


def load_config(config_path: Path) -> AppConfig:
    config_path = Path(config_path)
    if not config_path.is_file():
        return AppConfig()
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return AppConfig()
    if not isinstance(raw, dict):
        return AppConfig()

    return AppConfig(
        characters_dir=str(raw.get("characters_dir") or default_characters_dir()),
        custom_dirs=[str(x) for x in raw.get("custom_dirs", []) if x],
        installed_indexes=[dict(x) for x in raw.get("installed_indexes", []) if isinstance(x, dict)],
        favorites=[str(x) for x in raw.get("favorites", []) if x],
        auto_imported_official=bool(raw.get("auto_imported_official", False)),
    )


def save_config(config: AppConfig, config_path: Path) -> None:
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(asdict(config), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
