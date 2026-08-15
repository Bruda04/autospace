# autospace GNOME Shell extension

This extension exposes a small session D-Bus API that lets the `autospace` CLI
list windows and move them between workspaces on GNOME Wayland.

It also supports event-driven placement through `PlaceMatchingWindow`, which
waits inside GNOME Shell for matching windows and then applies monitor,
workspace, and maximized state. `ListMonitors` exposes GNOME Shell's monitor
order and primary monitor so the CLI can support `monitor: primary`.

Install locally:

```bash
mkdir -p ~/.local/share/gnome-shell/extensions
cp -r gnome-extension/autospace@local ~/.local/share/gnome-shell/extensions/
gnome-extensions enable autospace@local
```

Log out and back in if GNOME does not pick up the extension immediately.
