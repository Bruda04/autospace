import Gio from "gi://Gio";
import GLib from "gi://GLib";
import Meta from "gi://Meta";
import {Extension} from "resource:///org/gnome/shell/extensions/extension.js";

const BUS_NAME = "org.autospace.WindowControl";
const OBJECT_PATH = "/org/autospace/WindowControl";
const NO_MONITOR_INDEX = -1;
const PRIMARY_MONITOR_INDEX = -2;

const IFACE_XML = `
<node>
  <interface name="org.autospace.WindowControl">
    <method name="ListWindows">
      <arg type="s" direction="out" name="windows_json"/>
    </method>
    <method name="ListMonitors">
      <arg type="s" direction="out" name="monitors_json"/>
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
    <method name="PlaceMatchingWindow">
      <arg type="s" direction="in" name="match_json"/>
      <arg type="i" direction="in" name="workspace_index"/>
      <arg type="i" direction="in" name="monitor_index"/>
      <arg type="b" direction="in" name="maximized"/>
      <arg type="i" direction="in" name="timeout_ms"/>
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
    this._pendingPlacements = [];
    this._reconcileIntervalMs = 500;
    this._signalIds = [];
    this._connectWindowSignals();
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
      maximized: window.get_maximized?.() === Meta.MaximizeFlags.BOTH,
      fullscreen: window.is_fullscreen?.() ?? window.fullscreen ?? false,
    }));
    return JSON.stringify(windows);
  }

  ListMonitors() {
    const primaryMonitor = global.display.get_primary_monitor();
    const monitors = [];
    for (let index = 0; index < global.display.get_n_monitors(); index++) {
      const geometry = global.display.get_monitor_geometry(index);
      monitors.push({
        index,
        primary: index === primaryMonitor,
        x: geometry.x,
        y: geometry.y,
        width: geometry.width,
        height: geometry.height,
      });
    }
    return JSON.stringify(monitors);
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
    return window.get_workspace?.()?.index() === workspaceIndex;
  }

  MoveWindowToMonitor(windowId, monitorIndex) {
    this._refreshWindows();
    const window = this._windowsById.get(windowId);
    if (!window)
      return false;

    const resolvedMonitorIndex = this._resolveMonitorIndex(monitorIndex);
    const monitorCount = global.display.get_n_monitors();
    if (resolvedMonitorIndex < 0 || resolvedMonitorIndex >= monitorCount)
      return false;

    if (!this._moveWindowToMonitor(window, resolvedMonitorIndex))
      return false;
    return window.get_monitor?.() === resolvedMonitorIndex;
  }

  PlaceMatchingWindow(matchJson, workspaceIndex, monitorIndex, maximized, timeoutMs) {
    let match;
    try {
      match = JSON.parse(matchJson);
    } catch {
      return false;
    }

    if (!this._validWorkspace(workspaceIndex))
      return false;
    const resolvedMonitorIndex = this._resolveMonitorIndex(monitorIndex);
    if (resolvedMonitorIndex !== NO_MONITOR_INDEX && !this._validMonitor(resolvedMonitorIndex))
      return false;

    const placement = {
      match,
      workspaceIndex,
      monitorIndex,
      maximized,
      timeoutId: 0,
      reconcileId: 0,
    };
    placement.timeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, Math.max(1, timeoutMs), () => {
      placement.timeoutId = 0;
      this._removePendingPlacement(placement, {removeSources: false});
      return GLib.SOURCE_REMOVE;
    });
    placement.reconcileId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, this._reconcileIntervalMs, () => {
      this._reconcilePlacement(placement);
      return this._pendingPlacements.includes(placement) ? GLib.SOURCE_CONTINUE : GLib.SOURCE_REMOVE;
    });
    this._pendingPlacements.push(placement);
    this._reconcilePlacement(placement);
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

  _connectWindowSignals() {
    this._signalIds.push([global.display, global.display.connect('window-created', (_display, window) => {
      this._handleWindowEvent(window);
    })]);

    const manager = global.workspace_manager;
    for (let i = 0; i < manager.get_n_workspaces(); i++) {
      const workspace = manager.get_workspace_by_index(i);
      this._signalIds.push([workspace, workspace.connect('window-added', (_workspace, window) => {
        this._handleWindowEvent(window);
      })]);
    }
  }

  disconnectSignals() {
    for (const [object, signalId] of this._signalIds)
      object.disconnect(signalId);
    this._signalIds = [];
    for (const placement of [...this._pendingPlacements]) {
      this._removePendingPlacement(placement);
    }
    this._pendingPlacements = [];
  }

  _handleWindowEvent(window) {
    if (!window || this._pendingPlacements.length === 0)
      return;

    for (const placement of [...this._pendingPlacements]) {
      try {
        if (!this._windowMatches(window, placement.match))
          continue;

        this._placeWindow(window, placement.workspaceIndex, placement.monitorIndex, placement.maximized);
      } catch (error) {
        logError(error, "autospace failed to place a newly created window");
      }
    }
  }

  _reconcilePlacement(placement) {
    this._refreshWindows();
    for (const window of this._windowsById.values()) {
      try {
        if (!this._windowMatches(window, placement.match))
          continue;

        this._placeWindow(window, placement.workspaceIndex, placement.monitorIndex, placement.maximized);
      } catch (error) {
        logError(error, "autospace failed to reconcile window placement");
      }
    }
  }

  _windowMatches(window, match) {
    if (!window || window.skip_taskbar || window.get_window_type() !== Meta.WindowType.NORMAL)
      return false;
    if (match.app_id && this._normalize(window.get_gtk_application_id?.()) !== this._normalize(match.app_id))
      return false;
    if (match.wm_class && this._normalize(window.get_wm_class()) !== this._normalize(match.wm_class))
      return false;
    if (match.title && !this._normalize(window.get_title()).includes(this._normalize(match.title)))
      return false;
    if (match.pid !== undefined && match.pid !== null && window.get_pid?.() !== match.pid)
      return false;
    return true;
  }

  _placeWindow(window, workspaceIndex, monitorIndex, maximized) {
    if (!window || window.skip_taskbar || window.get_window_type() !== Meta.WindowType.NORMAL)
      return;

    const resolvedMonitorIndex = this._resolveMonitorIndex(monitorIndex);
    if (resolvedMonitorIndex >= 0 && window.get_monitor?.() !== resolvedMonitorIndex)
      this._moveWindowToMonitor(window, resolvedMonitorIndex);

    this._queuePlacementStep(() => {
      if (window.get_workspace?.()?.index() !== workspaceIndex)
        window.change_workspace_by_index(workspaceIndex, false);
      this._queuePlacementStep(() => {
        if (window.get_workspace?.()?.index() !== workspaceIndex)
          window.change_workspace_by_index(workspaceIndex, false);
        if (maximized)
          this._maximizeWindow(window);
      });
    });
  }

  _queuePlacementStep(callback) {
    GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
      try {
        callback();
      } catch (error) {
        logError(error, "autospace failed to run queued placement step");
      }
      return GLib.SOURCE_REMOVE;
    });
  }

  _maximizeWindow(window) {
    if (window.get_maximized?.() === Meta.MaximizeFlags.BOTH)
      return;
    if (window.maximize.length === 0)
      window.maximize();
    else
      window.maximize(Meta.MaximizeFlags.BOTH);
  }

  _moveWindowToMonitor(window, monitorIndex) {
    const geometry = global.display.get_monitor_geometry(monitorIndex);
    const frame = window.get_frame_rect?.();
    if (!geometry || !frame || frame.width <= 0 || frame.height <= 0)
      return false;

    const width = Math.min(frame.width, geometry.width);
    const height = Math.min(frame.height, geometry.height);
    const x = geometry.x + Math.max(0, Math.floor((geometry.width - width) / 2));
    const y = geometry.y + Math.max(0, Math.floor((geometry.height - height) / 2));
    window.move_frame(false, x, y);
    return true;
  }

  _removePendingPlacement(placement, {removeSources = true} = {}) {
    const index = this._pendingPlacements.indexOf(placement);
    if (index !== -1)
      this._pendingPlacements.splice(index, 1);
    if (removeSources && placement.timeoutId) {
      GLib.source_remove(placement.timeoutId);
    }
    if (removeSources && placement.reconcileId) {
      GLib.source_remove(placement.reconcileId);
    }
    placement.timeoutId = 0;
    placement.reconcileId = 0;
  }

  _validWorkspace(workspaceIndex) {
    const manager = global.workspace_manager;
    return workspaceIndex >= 0 && workspaceIndex < manager.get_n_workspaces();
  }

  _validMonitor(monitorIndex) {
    return monitorIndex >= 0 && monitorIndex < global.display.get_n_monitors();
  }

  _resolveMonitorIndex(monitorIndex) {
    if (monitorIndex === PRIMARY_MONITOR_INDEX)
      return global.display.get_primary_monitor();
    return monitorIndex;
  }

  _normalize(value) {
    return String(value ?? '').toLocaleLowerCase();
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
    if (this._service)
      this._service.disconnectSignals();
    this._service = null;
  }
}
