from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

MonitorTarget = int | Literal["primary"]


@dataclass(frozen=True)
class MatchRule:
    app_id: str | None = None
    wm_class: str | None = None
    title: str | None = None
    pid: int | None = None

    @classmethod
    def from_dict(cls, data: Any) -> "MatchRule":
        if not isinstance(data, dict):
            raise ValueError("match must be a mapping")

        rule = cls(
            app_id=_optional_str(data, "app_id"),
            wm_class=_optional_str(data, "wm_class"),
            title=_optional_str(data, "title"),
            pid=_optional_int(data, "pid"),
        )
        if not any((rule.app_id, rule.wm_class, rule.title, rule.pid is not None)):
            raise ValueError("match must define at least one of app_id, wm_class, title, pid")
        return rule


@dataclass(frozen=True)
class AppConfig:
    name: str
    command: str
    workspace: int
    match: MatchRule
    monitor: MonitorTarget | None = None
    maximized: bool = False
    delay: float = 0.0
    timeout: float = 20.0
    focus: bool = False
    reuse_existing: bool = False
    restart_if_no_window: bool = False

    @classmethod
    def from_dict(cls, data: Any) -> "AppConfig":
        if not isinstance(data, dict):
            raise ValueError("app entry must be a mapping")

        name = _required_str(data, "name")
        command = _required_str(data, "command")
        workspace = _required_int(data, "workspace")
        if workspace < 1:
            raise ValueError(f"{name}: workspace must be >= 1")
        monitor = _optional_monitor(data, "monitor")
        if isinstance(monitor, int) and monitor < 1:
            raise ValueError(f"{name}: monitor must be >= 1")

        delay = _optional_float(data, "delay", default=0.0)
        timeout = _optional_float(data, "timeout", default=20.0)
        if delay < 0:
            raise ValueError(f"{name}: delay must be >= 0")
        if timeout <= 0:
            raise ValueError(f"{name}: timeout must be > 0")

        return cls(
            name=name,
            command=command,
            workspace=workspace,
            monitor=monitor,
            maximized=_optional_bool(data, "maximized", default=False),
            match=MatchRule.from_dict(data.get("match")),
            delay=delay,
            timeout=timeout,
            focus=_optional_bool(data, "focus", default=False),
            reuse_existing=_optional_bool(data, "reuse_existing", default=False),
            restart_if_no_window=_optional_bool(data, "restart_if_no_window", default=False),
        )


@dataclass(frozen=True)
class Preset:
    name: str
    apps: list[AppConfig] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Any) -> "Preset":
        if not isinstance(data, dict):
            raise ValueError("preset must be a mapping")

        name = _required_str(data, "name")
        apps_data = data.get("apps")
        if not isinstance(apps_data, list) or not apps_data:
            raise ValueError("preset apps must be a non-empty list")

        return cls(name=name, apps=[AppConfig.from_dict(app) for app in apps_data])


@dataclass(frozen=True)
class Window:
    id: str
    title: str | None = None
    app_id: str | None = None
    wm_class: str | None = None
    pid: int | None = None
    workspace: int | None = None
    monitor: int | None = None
    maximized: bool | None = None
    fullscreen: bool | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Window":
        return cls(
            id=str(data["id"]),
            title=_coerce_optional_str(data.get("title")),
            app_id=_coerce_optional_str(data.get("app_id")),
            wm_class=_coerce_optional_str(data.get("wm_class")),
            pid=_coerce_optional_int(data.get("pid")),
            workspace=_coerce_optional_int(data.get("workspace")),
            monitor=_coerce_optional_int(data.get("monitor")),
            maximized=_coerce_optional_bool(data.get("maximized")),
            fullscreen=_coerce_optional_bool(data.get("fullscreen")),
        )


@dataclass(frozen=True)
class Monitor:
    index: int
    primary: bool = False
    x: int | None = None
    y: int | None = None
    width: int | None = None
    height: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Monitor":
        return cls(
            index=_coerce_required_int(data.get("index"), field_name="index"),
            primary=_coerce_optional_bool(data.get("primary")) or False,
            x=_coerce_optional_int(data.get("x")),
            y=_coerce_optional_int(data.get("y")),
            width=_coerce_optional_int(data.get("width")),
            height=_coerce_optional_int(data.get("height")),
        )


def _required_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_str(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string when provided")
    return value


def _required_int(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _optional_int(data: dict[str, Any], key: str) -> int | None:
    value = data.get(key)
    return _coerce_optional_int(value, field_name=key)


def _optional_monitor(data: dict[str, Any], key: str) -> MonitorTarget | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        if value.strip().casefold() == "primary":
            return "primary"
        raise ValueError(f"{key} must be an integer or 'primary'")
    return _coerce_optional_int(value, field_name=key)


def _optional_float(data: dict[str, Any], key: str, *, default: float) -> float:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    return float(value)


def _optional_bool(data: dict[str, Any], key: str, *, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be true or false")
    return value


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _coerce_optional_int(value: Any, *, field_name: str = "value") -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


def _coerce_required_int(value: Any, *, field_name: str = "value") -> int:
    coerced = _coerce_optional_int(value, field_name=field_name)
    if coerced is None:
        raise ValueError(f"{field_name} must be an integer")
    return coerced


def _coerce_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError("value must be true or false")
    return value
