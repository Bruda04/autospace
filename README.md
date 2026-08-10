# autospace

`autospace` is a small Linux CLI for launching groups of desktop applications
and moving their windows to configured workspaces.

It is intended for repeatable desktop setups: work sessions, development
contexts, streaming setups, research workflows, or any routine where the same
applications should open in the same places.

## Features

- Launch application presets from YAML files.
- Move windows to configured workspaces.
- Optionally target monitors on GNOME Wayland.
- Reuse existing windows instead of launching duplicates.
- Run applications detached from the terminal, with application logs redirected
  away from the shell.
- Support GNOME Wayland through a bundled GNOME Shell extension bridge.
- Support X11 workspace moves through `wmctrl`.

## Requirements

- Linux
- Python 3.10+
- `PyYAML`
- `gdbus` for GNOME Wayland integration
- `wmctrl` for X11 fallback

GNOME Wayland requires the bundled Shell extension because normal user-space
tools cannot reliably move arbitrary windows on Wayland.

## Installation

From the repository root:

```bash
scripts/install.sh
```

The default installation writes the application to:

```text
/opt/autospace
```

and creates:

```text
/usr/local/bin/autospace
```

Install the example presets:

```bash
scripts/install.sh --install-example-config
```

Install the GNOME Shell extension bridge:

```bash
scripts/install.sh --install-gnome-extension
```

Install both:

```bash
scripts/install.sh --install-example-config --install-gnome-extension
```

If GNOME does not load the extension immediately, disable/enable it or log out
and back in:

```bash
gnome-extensions disable autospace@local
gnome-extensions enable autospace@local
```

## Uninstall

```bash
scripts/uninstall.sh
```

Remove user configuration and the GNOME extension as well:

```bash
scripts/uninstall.sh --remove-config --remove-gnome-extension
```

## Usage

List presets:

```bash
autospace list
```

Check desktop backend availability:

```bash
autospace check
```

Validate a preset:

```bash
autospace validate work
```

Run a preset:

```bash
autospace run work
```

Run a preset without per-application output:

```bash
autospace run --quiet work
autospace run -q work
```

`--quiet` is only supported on the `run` subcommand. It suppresses normal
per-application result lines, but exit codes are preserved.

## Configuration

Presets are loaded from:

```text
~/.config/autospace/presets/*.yaml
```

Use `--config-dir` to point at another config directory:

```bash
autospace --config-dir examples list
autospace --config-dir examples validate work
autospace --config-dir examples run work
```

Example preset:

```yaml
name: work
apps:
  - name: Firefox
    command: firefox
    workspace: 1
    monitor: 1
    reuse_existing: true
    match:
      wm_class: firefox

  - name: Editor
    command: code /home/user/projects/example
    workspace: 2
    monitor: 1
    match:
      wm_class: code
```

Supported app fields:

- `name`: human-readable application name.
- `command`: command used to launch the application.
- `workspace`: target workspace, 1-based.
- `monitor`: optional target monitor, 1-based.
- `reuse_existing`: move an existing matching window instead of launching a new
  one.
- `focus`: focus the window after moving it.
- `delay`: seconds to wait immediately after launching before polling.
- `timeout`: seconds to wait for a matching window.
- `match`: window matching rule.

Supported match keys:

- `wm_class`
- `app_id`
- `title`
- `pid`

At least one match key is required.

## Backends

### GNOME Wayland

GNOME Wayland support uses the bundled extension in
`gnome-extension/autospace@local`. The extension exposes a small session D-Bus
API used by the CLI:

- `ListWindows()`
- `MoveWindowToWorkspace(window_id, workspace_index)`
- `MoveWindowToMonitor(window_id, monitor_index)`
- `ActivateWindow(window_id)`

The YAML config uses 1-based workspace and monitor numbers. The backend API uses
0-based indices internally.

### X11

X11 support uses `wmctrl` for listing windows and moving them between
workspaces.

Monitor targeting is not supported by the X11 backend in this version.

## Limitations

- Linux only.
- GNOME Wayland requires the bundled GNOME Shell extension.
- X11 support depends on `wmctrl`.
- Monitor targeting currently works only with the GNOME Wayland backend.
- Window matching depends on each application's exposed `wm_class`, `app_id`,
  title, or process id.

## Development

Install locally:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

Run smoke checks:

```bash
python3 -m compileall src
autospace --help
autospace run --help
autospace --config-dir examples list
autospace --config-dir examples validate work
bash -n scripts/install.sh scripts/uninstall.sh
```

## Contributing

Issues and pull requests are welcome. Please keep changes focused and include a
clear description of the desktop environment, session type, and backend involved
when reporting window-management behavior.

Before opening a pull request, run the smoke checks above and verify the
behavior manually on the desktop environment affected by the change.

## License

MIT. See [LICENSE](LICENSE).
