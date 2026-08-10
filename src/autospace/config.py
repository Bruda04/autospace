from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from autospace.models import Preset


DEFAULT_CONFIG_DIR = Path.home() / ".config" / "autospace"


def config_dir_from_env(env: dict[str, str]) -> Path:
    if env.get("AUTOSPACE_CONFIG_DIR"):
        return Path(env["AUTOSPACE_CONFIG_DIR"]).expanduser()
    if env.get("XDG_CONFIG_HOME"):
        return Path(env["XDG_CONFIG_HOME"]).expanduser() / "autospace"
    return DEFAULT_CONFIG_DIR


def presets_dir(config_dir: Path) -> Path:
    return config_dir / "presets"


def preset_path(config_dir: Path, preset_name: str) -> Path:
    if "/" in preset_name or "\\" in preset_name or preset_name in {"", ".", ".."}:
        raise ValueError("preset name must be a simple file name without path separators")
    return presets_dir(config_dir) / f"{preset_name}.yaml"


def list_presets(config_dir: Path) -> list[str]:
    directory = presets_dir(config_dir)
    if not directory.exists():
        return []
    return sorted(path.stem for path in directory.glob("*.yaml") if path.is_file())


def load_preset(config_dir: Path, preset_name: str) -> Preset:
    path = preset_path(config_dir, preset_name)
    if not path.exists():
        raise FileNotFoundError(f"preset not found: {path}")
    return parse_preset(path)


def parse_preset(path: Path) -> Preset:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data: Any = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML in {path}: {exc}") from exc

    try:
        return Preset.from_dict(data)
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from exc
