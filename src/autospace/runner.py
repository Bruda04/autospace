from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass

from autospace.backends import PRIMARY_MONITOR_INDEX, BackendError, WindowBackend
from autospace.matcher import window_matches
from autospace.models import AppConfig, Preset, Window
from autospace.processes import terminate_command_processes

FINAL_FOCUS_SETTLE_SECONDS = 1.0


@dataclass(frozen=True)
class AppResult:
    app: str
    ok: bool
    message: str


@dataclass(frozen=True)
class PreparedApp:
    window: Window | None
    should_launch: bool


def run_preset(preset: Preset, backend: WindowBackend, *, poll_interval: float = 0.5) -> list[AppResult]:
    if backend.name == "gnome-wayland":
        return run_preset_event_driven(preset, backend)

    results: list[AppResult] = []
    for app in preset.apps:
        results.append(run_app(app, backend, poll_interval=poll_interval))
    return results


def run_preset_event_driven(preset: Preset, backend: WindowBackend) -> list[AppResult]:
    setup_results: list[AppResult] = []
    apps_to_launch: list[AppConfig] = []
    scheduled_apps: list[AppConfig] = []
    launch_failed: set[str] = set()

    for app in preset.apps:
        try:
            prepared = prepare_app(app, backend)
            if not schedule_event_driven_placement(app, backend):
                return [run_app(item, backend) for item in preset.apps]
            if prepared.should_launch:
                apps_to_launch.append(app)
            scheduled_apps.append(app)
        except (BackendError, OSError, ValueError) as exc:
            setup_results.append(AppResult(app=app.name, ok=False, message=str(exc)))

    for app in apps_to_launch:
        try:
            launch_app(app.command)
        except (OSError, ValueError) as exc:
            launch_failed.add(app.name)
            setup_results.append(AppResult(app=app.name, ok=False, message=str(exc)))

    apps_to_verify = [app for app in scheduled_apps if app.name not in launch_failed]
    return [*setup_results, *wait_for_placements(backend, apps_to_verify)]


def run_app(app: AppConfig, backend: WindowBackend, *, poll_interval: float = 0.5) -> AppResult:
    try:
        prepared = prepare_app(app, backend)
        launched = prepared.should_launch
        window = prepared.window
        if launched:
            launch_app(app.command)
            if app.delay:
                time.sleep(app.delay)

        if schedule_event_driven_placement(app, backend):
            return wait_for_placement(backend, app, poll_interval=poll_interval)

        if launched:
            window = wait_for_window(backend, app, poll_interval=poll_interval)
        if window is None:
            return AppResult(app=app.name, ok=False, message=f"window not found within {app.timeout:g}s")

        if app.monitor is not None:
            monitor_index = monitor_index_for_backend(backend, app)
            backend.move_to_monitor(window.id, monitor_index)
            time.sleep(0.2)
        backend.move_to_workspace(window.id, app.workspace - 1)
        if app.monitor is not None:
            time.sleep(0.2)
            backend.move_to_workspace(window.id, app.workspace - 1)
        if app.focus:
            backend.activate(window.id)
        return AppResult(app=app.name, ok=True, message=f"moved to {location_label(app)}")
    except (BackendError, OSError, ValueError) as exc:
        return AppResult(app=app.name, ok=False, message=str(exc))


def prepare_app(app: AppConfig, backend: WindowBackend) -> PreparedApp:
    window = find_window(backend, app)
    if window is None and app.restart_if_no_window:
        terminate_command_processes(app.command)
    return PreparedApp(window=window, should_launch=window is None or not app.reuse_existing)


def schedule_event_driven_placement(app: AppConfig, backend: WindowBackend) -> bool:
    try:
        backend.place_matching_window(
            app.match,
            app.workspace - 1,
            monitor_index_for_backend(backend, app),
            app.maximized,
            app.timeout,
        )
    except BackendError:
        return False
    return True


def wait_for_placements(
    backend: WindowBackend,
    apps: list[AppConfig],
    *,
    poll_interval: float = 0.5,
) -> list[AppResult]:
    pending = {app.name: app for app in apps}
    results: list[AppResult] = []
    deadlines = {app.name: time.monotonic() + app.timeout for app in apps}
    last_seen: dict[str, Window] = {}
    placed_windows: dict[str, Window] = {}
    expected_monitors: dict[str, int | None] = {}

    for app_name, app in list(pending.items()):
        try:
            expected_monitors[app_name] = expected_monitor_index(backend, app)
        except BackendError as exc:
            results.append(AppResult(app=app.name, ok=False, message=str(exc)))
            pending.pop(app_name)

    while pending:
        now = time.monotonic()
        try:
            windows = backend.list_windows()
        except BackendError as exc:
            results.extend(AppResult(app=app.name, ok=False, message=str(exc)) for app in pending.values())
            break
        for app_name, app in list(pending.items()):
            matching = [window for window in windows if window_matches(window, app.match)]
            if matching:
                last_seen[app_name] = matching[0]
            placed = next(
                (window for window in matching if window_is_placed(app, window, expected_monitors[app_name])),
                None,
            )
            if placed is not None:
                placed_windows[app_name] = placed
                results.append(AppResult(app=app.name, ok=True, message=f"placed in {location_label(app)}"))
                pending.pop(app_name)
                continue
            if now > deadlines[app_name]:
                detail = last_seen_label(last_seen.get(app_name))
                results.append(
                    AppResult(
                        app=app.name,
                        ok=False,
                        message=f"window not placed within {app.timeout:g}s{detail}",
                    )
                )
                pending.pop(app_name)
        if pending:
            time.sleep(poll_interval)

    focus_last_placed_app(backend, apps, placed_windows, expected_monitors)
    return results


def wait_for_placement(backend: WindowBackend, app: AppConfig, *, poll_interval: float) -> AppResult:
    return wait_for_placements(backend, [app], poll_interval=poll_interval)[0]


def focus_last_placed_app(
    backend: WindowBackend,
    apps: list[AppConfig],
    placed_windows: dict[str, Window],
    expected_monitors: dict[str, int | None],
) -> None:
    focused_apps = [app for app in apps if app.focus and app.name in placed_windows]
    if not focused_apps:
        return

    app = focused_apps[-1]
    focus_matching_app(backend, app, expected_monitors.get(app.name))
    time.sleep(FINAL_FOCUS_SETTLE_SECONDS)
    focus_matching_app(backend, app, expected_monitors.get(app.name))


def focus_matching_app(backend: WindowBackend, app: AppConfig, expected_monitor: int | None) -> None:
    matching = [window for window in backend.list_windows() if window_matches(window, app.match)]
    placed = next((window for window in matching if window_is_placed(app, window, expected_monitor)), None)
    if placed is not None:
        backend.activate(placed.id)


def window_is_placed(app: AppConfig, window: Window, expected_monitor: int | None) -> bool:
    if window.workspace != app.workspace - 1:
        return False
    if expected_monitor is not None and window.monitor != expected_monitor:
        return False
    return True


def monitor_index_for_backend(backend: WindowBackend, app: AppConfig) -> int | None:
    if app.monitor is None:
        return None
    if app.monitor == "primary":
        if backend.name == "gnome-wayland":
            return PRIMARY_MONITOR_INDEX
        raise BackendError("monitor: primary requires the GNOME Wayland backend")
    return app.monitor - 1


def expected_monitor_index(backend: WindowBackend, app: AppConfig) -> int | None:
    if app.monitor is None:
        return None
    if app.monitor == "primary":
        for monitor in backend.list_monitors():
            if monitor.primary:
                return monitor.index
        raise BackendError("primary monitor was not reported by the backend")
    return app.monitor - 1


def location_label(app: AppConfig) -> str:
    location = f"workspace {app.workspace}"
    if app.monitor is not None:
        location = f"{location}, monitor {app.monitor}"
    return location


def last_seen_label(window: Window | None) -> str:
    if window is None:
        return ""
    parts: list[str] = []
    if window.workspace is not None:
        parts.append(f"last seen workspace {window.workspace + 1}")
    if window.monitor is not None:
        parts.append(f"monitor {window.monitor + 1}")
    if not parts:
        return ""
    return f" ({', '.join(parts)})"


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
