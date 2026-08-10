from __future__ import annotations

import argparse
import os
import sys

from autospace.backends import BackendUnavailable, backend_report, detect_backend
from autospace.config import config_dir_from_env, list_presets, load_preset, parse_preset, preset_path
from autospace.runner import run_preset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autospace")
    parser.add_argument(
        "--config-dir",
        help="config directory, defaults to $AUTOSPACE_CONFIG_DIR or ~/.config/autospace",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="list available presets")
    subparsers.add_parser("check", help="check desktop session and backend availability")

    validate = subparsers.add_parser("validate", help="validate a preset without running it")
    validate.add_argument("preset")

    run = subparsers.add_parser("run", help="run a preset")
    run.add_argument("-q", "--quiet", action="store_true", help="suppress per-application run output")
    run.add_argument("preset")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_dir = _config_dir(args)

    if args.command == "list":
        presets = list_presets(config_dir)
        if not presets:
            print(f"no presets found in {config_dir / 'presets'}")
            return 1
        for preset in presets:
            print(preset)
        return 0

    if args.command == "check":
        print(f"config directory: {config_dir}")
        print(f"presets: {len(list_presets(config_dir))}")
        for line in backend_report(os.environ):
            print(line)
        return 0

    if args.command == "validate":
        try:
            preset = parse_preset(preset_path(config_dir, args.preset))
        except (FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"valid preset: {preset.name} ({len(preset.apps)} apps)")
        return 0

    if args.command == "run":
        try:
            preset = load_preset(config_dir, args.preset)
            backend = detect_backend(os.environ)
        except (FileNotFoundError, ValueError, BackendUnavailable) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        results = run_preset(preset, backend)
        failed = False
        for result in results:
            if not args.quiet:
                status = "ok" if result.ok else "failed"
                print(f"{status}: {result.app}: {result.message}")
            failed = failed or not result.ok
        return 1 if failed else 0

    return 2


def _config_dir(args: argparse.Namespace):
    if args.config_dir:
        from pathlib import Path

        return Path(args.config_dir).expanduser()
    return config_dir_from_env(os.environ)
