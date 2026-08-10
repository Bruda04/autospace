from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass

from autospace.backends import BackendError, WindowBackend
from autospace.matcher import window_matches
from autospace.models import AppConfig, Preset, Window


@dataclass(frozen=True)
class AppResult:
    app: str
    ok: bool
    message: str


def run_preset(preset: Preset, backend: WindowBackend, *, poll_interval: float = 0.5) -> list[AppResult]:
    results: list[AppResult] = []
    for app in preset.apps:
        results.append(run_app(app, backend, poll_interval=poll_interval))
    return results


def run_app(app: AppConfig, backend: WindowBackend, *, poll_interval: float = 0.5) -> AppResult:
    try:
        window = find_window(backend, app)
        if window is None:
            launch_app(app.command)
            if app.delay:
                time.sleep(app.delay)
            window = wait_for_window(backend, app, poll_interval=poll_interval)
        elif not app.reuse_existing:
            launch_app(app.command)
            if app.delay:
                time.sleep(app.delay)
            window = wait_for_window(backend, app, poll_interval=poll_interval)

        if window is None:
            return AppResult(app=app.name, ok=False, message=f"window not found within {app.timeout:g}s")

        backend.move_to_workspace(window.id, app.workspace - 1)
        if app.monitor is not None:
            backend.move_to_monitor(window.id, app.monitor - 1)
        if app.focus:
            backend.activate(window.id)
        location = f"workspace {app.workspace}"
        if app.monitor is not None:
            location = f"{location}, monitor {app.monitor}"
        return AppResult(app=app.name, ok=True, message=f"moved to {location}")
    except (BackendError, OSError, ValueError) as exc:
        return AppResult(app=app.name, ok=False, message=str(exc))


def launch_app(command: str) -> None:
    subprocess.Popen(
        shlex.split(command),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def wait_for_window(backend: WindowBackend, app: AppConfig, *, poll_interval: float) -> Window | None:
    deadline = time.monotonic() + app.timeout
    while time.monotonic() <= deadline:
        window = find_window(backend, app)
        if window is not None:
            return window
        time.sleep(poll_interval)
    return None


def find_window(backend: WindowBackend, app: AppConfig) -> Window | None:
    for window in backend.list_windows():
        if window_matches(window, app.match):
            return window
    return None
