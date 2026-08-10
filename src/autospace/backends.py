from __future__ import annotations

import json
import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass

from autospace.models import Window


class BackendError(RuntimeError):
    pass


class BackendUnavailable(BackendError):
    pass


class WindowBackend(ABC):
    name: str

    @abstractmethod
    def available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list_windows(self) -> list[Window]:
        raise NotImplementedError

    @abstractmethod
    def move_to_workspace(self, window_id: str, workspace_index: int) -> None:
        raise NotImplementedError

    def move_to_monitor(self, window_id: str, monitor_index: int) -> None:
        raise BackendError(f"{self.name} does not support monitor targeting")

    def activate(self, window_id: str) -> None:
        return None

    def diagnostics(self) -> list[str]:
        return []


@dataclass
class GnomeWaylandBackend(WindowBackend):
    bus_name: str = "org.autospace.WindowControl"
    object_path: str = "/org/autospace/WindowControl"
    interface: str = "org.autospace.WindowControl"
    name: str = "gnome-wayland"

    def available(self) -> bool:
        if shutil.which("gdbus") is None:
            return False
        try:
            self._call("ListWindows", timeout=2)
        except BackendError:
            return False
        return True

    def diagnostics(self) -> list[str]:
        if shutil.which("gdbus") is None:
            return ["gdbus was not found"]
        if not self.available():
            return [
                "GNOME Wayland D-Bus service org.autospace.WindowControl is not available",
                "Install and enable the autospace GNOME Shell extension integration",
            ]
        return ["GNOME Wayland D-Bus service is available"]

    def list_windows(self) -> list[Window]:
        payload = self._call("ListWindows")
        try:
            data = json.loads(_unwrap_gdbus_string(payload))
            return [Window.from_dict(item) for item in data]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise BackendError(f"invalid ListWindows response: {payload}") from exc

    def move_to_workspace(self, window_id: str, workspace_index: int) -> None:
        result = self._call("MoveWindowToWorkspace", window_id, workspace_index)
        if "true" not in result.lower():
            raise BackendError(f"failed to move window {window_id} to workspace {workspace_index + 1}")

    def move_to_monitor(self, window_id: str, monitor_index: int) -> None:
        result = self._call("MoveWindowToMonitor", window_id, monitor_index)
        if "true" not in result.lower():
            raise BackendError(f"failed to move window {window_id} to monitor {monitor_index + 1}")

    def activate(self, window_id: str) -> None:
        self._call("ActivateWindow", window_id)

    def _call(self, method: str, *args: object, timeout: float = 10) -> str:
        command = [
            "gdbus",
            "call",
            "--session",
            "--dest",
            self.bus_name,
            "--object-path",
            self.object_path,
            "--method",
            f"{self.interface}.{method}",
        ]
        command.extend(_gvariant_arg(arg) for arg in args)
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BackendError(str(exc)) from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise BackendError(detail or f"gdbus call failed for {method}")
        return completed.stdout.strip()


@dataclass
class X11WmctrlBackend(WindowBackend):
    name: str = "x11-wmctrl"

    def available(self) -> bool:
        return shutil.which("wmctrl") is not None

    def diagnostics(self) -> list[str]:
        if self.available():
            return ["wmctrl is available"]
        return ["wmctrl was not found"]

    def list_windows(self) -> list[Window]:
        try:
            completed = subprocess.run(
                ["wmctrl", "-lx", "-p"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BackendError(str(exc)) from exc
        if completed.returncode != 0:
            raise BackendError(completed.stderr.strip() or "wmctrl -lx -p failed")

        windows: list[Window] = []
        for line in completed.stdout.splitlines():
            parts = line.split(None, 5)
            if len(parts) < 6:
                continue
            window_id, workspace_raw, pid_raw, wm_class, _host, title = parts
            workspace = None if workspace_raw == "-1" else int(workspace_raw)
            pid = None if pid_raw == "0" else int(pid_raw)
            windows.append(
                Window(
                    id=window_id,
                    title=title,
                    wm_class=wm_class.split(".")[-1],
                    app_id=wm_class,
                    pid=pid,
                    workspace=workspace,
                    monitor=None,
                )
            )
        return windows

    def move_to_workspace(self, window_id: str, workspace_index: int) -> None:
        self._wmctrl(["-ir", window_id, "-t", str(workspace_index)])

    def activate(self, window_id: str) -> None:
        self._wmctrl(["-ia", window_id])

    def _wmctrl(self, args: list[str]) -> None:
        completed = subprocess.run(["wmctrl", *args], check=False, capture_output=True, text=True, timeout=10)
        if completed.returncode != 0:
            raise BackendError(completed.stderr.strip() or f"wmctrl {' '.join(args)} failed")


def detect_backend(env: dict[str, str] | None = None) -> WindowBackend:
    env = env or os.environ
    session_type = env.get("XDG_SESSION_TYPE", "").casefold()
    desktop = env.get("XDG_CURRENT_DESKTOP", "").casefold()

    candidates: list[WindowBackend]
    if session_type == "wayland" and "gnome" in desktop:
        candidates = [GnomeWaylandBackend(), X11WmctrlBackend()]
    elif session_type == "x11":
        candidates = [X11WmctrlBackend()]
    else:
        candidates = [GnomeWaylandBackend(), X11WmctrlBackend()]

    for backend in candidates:
        if backend.available():
            return backend

    names = ", ".join(backend.name for backend in candidates)
    raise BackendUnavailable(f"no available backend found; tried {names}")


def backend_report(env: dict[str, str] | None = None) -> list[str]:
    env = env or os.environ
    lines = [
        f"session type: {env.get('XDG_SESSION_TYPE', 'unknown')}",
        f"desktop: {env.get('XDG_CURRENT_DESKTOP', 'unknown')}",
    ]
    for backend in (GnomeWaylandBackend(), X11WmctrlBackend()):
        status = "available" if backend.available() else "unavailable"
        lines.append(f"{backend.name}: {status}")
        lines.extend(f"  - {line}" for line in backend.diagnostics())
    return lines


def _unwrap_gdbus_string(output: str) -> str:
    value = output.strip()
    if value.startswith("('") and value.endswith("',)"):
        return bytes(value[2:-3], "utf-8").decode("unicode_escape")
    if value.startswith('("') and value.endswith('",)'):
        return bytes(value[2:-3], "utf-8").decode("unicode_escape")
    return value


def _gvariant_arg(value: object) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    return str(value)
