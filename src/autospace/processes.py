from __future__ import annotations

import os
import shlex
import shutil
import signal
import time
from pathlib import Path


def terminate_command_processes(command: str, *, timeout: float = 5.0) -> int:
    executable = executable_for_command(command)
    if executable is None:
        return 0

    current_pid = os.getpid()
    pids = [pid for pid in matching_executable_pids(executable) if pid != current_pid]
    if not pids:
        return 0

    for pid in pids:
        send_signal(pid, signal.SIGTERM)

    deadline = time.monotonic() + timeout
    remaining = pids
    while remaining and time.monotonic() < deadline:
        time.sleep(0.1)
        remaining = [pid for pid in remaining if process_exists(pid)]

    for pid in remaining:
        send_signal(pid, signal.SIGKILL)

    return len(pids)


def executable_for_command(command: str) -> Path | None:
    parts = shlex.split(command)
    if not parts:
        return None

    executable = parts[0]
    resolved = shutil.which(executable) if "/" not in executable else executable
    if resolved is None:
        return None

    return Path(resolved).expanduser().resolve()


def matching_executable_pids(executable: Path) -> list[int]:
    pids: list[int] = []
    for proc_dir in Path("/proc").iterdir():
        if not proc_dir.name.isdigit():
            continue
        pid = int(proc_dir.name)
        if process_executable(proc_dir) == executable:
            pids.append(pid)
    return pids


def process_executable(proc_dir: Path) -> Path | None:
    try:
        return (proc_dir / "exe").resolve()
    except (FileNotFoundError, PermissionError, OSError):
        return None


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def send_signal(pid: int, sig: signal.Signals) -> None:
    try:
        os.kill(pid, sig)
    except (ProcessLookupError, PermissionError):
        return
