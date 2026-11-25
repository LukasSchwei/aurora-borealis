"""Persistent application configuration for Aurora Borealis."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .paths import get_default_characters_dir

UI_ZOOM_STAGES: tuple[tuple[float, str], ...] = (
    (0.8, "Compact"),
    (0.9, "Small"),
    (1.0, "Normal"),
    (1.1, "Large"),
    (1.2, "Extra Large"),
)


def snap_ui_scale(scale: float) -> float:
    """Snap any UI scale float to the nearest supported zoom stage."""
    try:
        val = float(scale)
    except (TypeError, ValueError):
        return 1.0
    return min(UI_ZOOM_STAGES, key=lambda st: (abs(st[0] - val), st[0]))[0]


def get_zoom_stage_index(scale: float) -> int:
    """Return the index (0..4) of the zoom stage matching ``scale``."""
    snapped = snap_ui_scale(scale)
    for idx, (val, _name) in enumerate(UI_ZOOM_STAGES):
        if abs(val - snapped) < 1e-6:
            return idx
    return 2


def get_zoom_stage_label(scale: float) -> str:
    """Return human-readable zoom stage label like ``'Normal (100%)'``."""
    idx = get_zoom_stage_index(scale)
    val, name = UI_ZOOM_STAGES[idx]
    return f"{name} ({round(val * 100)}%)"


def default_characters_dir() -> str:
    return str(get_default_characters_dir())


@dataclass
class AppConfig:
    characters_dir: str = field(default_factory=default_characters_dir)
    custom_dirs: list[str] = field(default_factory=list)
    installed_indexes: list[dict] = field(default_factory=list)
    favorites: list[str] = field(default_factory=list)
    auto_imported_official: bool = False
    theme: str = "dark"
    ui_scale: float = 1.0
    enforce_attunement: bool = True


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

    try:
        raw_scale = float(raw.get("ui_scale", 1.0))
    except (TypeError, ValueError):
        raw_scale = 1.0
    ui_scale = snap_ui_scale(raw_scale)

    return AppConfig(
        characters_dir=str(raw.get("characters_dir") or default_characters_dir()),
        custom_dirs=[str(x) for x in raw.get("custom_dirs", []) if x],
        installed_indexes=[dict(x) for x in raw.get("installed_indexes", []) if isinstance(x, dict)],
        favorites=[str(x) for x in raw.get("favorites", []) if x],
        auto_imported_official=bool(raw.get("auto_imported_official", False)),
        theme="light" if str(raw.get("theme", "dark")).lower() == "light" else "dark",
        ui_scale=ui_scale,
        enforce_attunement=bool(raw.get("enforce_attunement", True)),
    )


def save_config(config: AppConfig, config_path: Path) -> None:
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(asdict(config), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
