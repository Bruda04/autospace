import Gio from "gi://Gio";
import GLib from "gi://GLib";
import Meta from "gi://Meta";
import {Extension} from "resource:///org/gnome/shell/extensions/extension.js";

const BUS_NAME = "org.autospace.WindowControl";
const OBJECT_PATH = "/org/autospace/WindowControl";

const IFACE_XML = `
<node>
  <interface name="org.autospace.WindowControl">
    <method name="ListWindows">
      <arg type="s" direction="out" name="windows_json"/>
    </method>
    <method name="MoveWindowToWorkspace">
      <arg type="s" direction="in" name="window_id"/>
      <arg type="i" direction="in" name="workspace_index"/>
      <arg type="b" direction="out" name="ok"/>
    </method>
    <method name="MoveWindowToMonitor">
      <arg type="s" direction="in" name="window_id"/>
      <arg type="i" direction="in" name="monitor_index"/>
      <arg type="b" direction="out" name="ok"/>
    </method>
    <method name="ActivateWindow">
      <arg type="s" direction="in" name="window_id"/>
      <arg type="b" direction="out" name="ok"/>
    </method>
  </interface>
</node>`;

class WindowControlService {
  constructor() {
    this._nextId = 1;
    this._idsBySignature = new Map();
    this._windowsById = new Map();
  }

  ListWindows() {
    this._refreshWindows();
    const windows = [...this._windowsById.entries()].map(([id, window]) => ({
      id,
      title: window.get_title() ?? null,
      app_id: window.get_gtk_application_id?.() ?? null,
      wm_class: window.get_wm_class() ?? null,
      pid: window.get_pid?.() ?? null,
      workspace: window.get_workspace()?.index() ?? null,
      monitor: window.get_monitor?.() ?? null,
    }));
    return JSON.stringify(windows);
  }

  MoveWindowToWorkspace(windowId, workspaceIndex) {
    this._refreshWindows();
    const window = this._windowsById.get(windowId);
    if (!window)
      return false;

    const manager = global.workspace_manager;
    const workspaceCount = manager.get_n_workspaces();
    if (workspaceIndex < 0 || workspaceIndex >= workspaceCount)
      return false;

    window.change_workspace_by_index(workspaceIndex, false);
    return true;
  }

  MoveWindowToMonitor(windowId, monitorIndex) {
    this._refreshWindows();
    const window = this._windowsById.get(windowId);
    if (!window)
      return false;

    const monitorCount = global.display.get_n_monitors();
    if (monitorIndex < 0 || monitorIndex >= monitorCount)
      return false;

    window.move_to_monitor(monitorIndex);
    return true;
  }

  ActivateWindow(windowId) {
    this._refreshWindows();
    const window = this._windowsById.get(windowId);
    if (!window)
      return false;

    window.activate(global.get_current_time());
    return true;
  }

  _refreshWindows() {
    const windows = global.get_window_actors()
      .map(actor => actor.meta_window)
      .filter(window => window && !window.skip_taskbar && window.get_window_type() === Meta.WindowType.NORMAL);

    const nextWindowsById = new Map();
    for (const window of windows) {
      const signature = this._signature(window);
      let id = this._idsBySignature.get(signature);
      if (!id) {
        id = `w${this._nextId++}`;
        this._idsBySignature.set(signature, id);
      }
      nextWindowsById.set(id, window);
    }
    this._windowsById = nextWindowsById;
  }

  _signature(window) {
    const pid = window.get_pid?.() ?? "";
    const wmClass = window.get_wm_class() ?? "";
    const title = window.get_title() ?? "";
    return `${pid}:${wmClass}:${title}`;
  }
}

export default class AutospaceExtension extends Extension {
  enable() {
    this._service = new WindowControlService();
    this._dbus = Gio.DBusExportedObject.wrapJSObject(IFACE_XML, this._service);
    this._dbus.export(Gio.DBus.session, OBJECT_PATH);
    this._busId = Gio.bus_own_name_on_connection(
      Gio.DBus.session,
      BUS_NAME,
      Gio.BusNameOwnerFlags.REPLACE,
      null,
      null
    );
  }

  disable() {
    if (this._busId) {
      Gio.bus_unown_name(this._busId);
      this._busId = null;
    }
    if (this._dbus) {
      this._dbus.unexport();
      this._dbus = null;
    }
    this._service = null;
  }
}
