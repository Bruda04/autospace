#!/usr/bin/env bash
set -euo pipefail

APP_NAME="autospace"
INSTALL_DIR="${INSTALL_DIR:-/opt/autospace}"
BIN_DIR="${BIN_DIR:-/usr/local/bin}"
REMOVE_CONFIG=0
REMOVE_GNOME_EXTENSION=0

usage() {
  cat <<USAGE
Usage: scripts/uninstall.sh [options]

Uninstalls autospace from the system.

Options:
  --remove-config          Remove ~/.config/autospace for the invoking user
  --remove-gnome-extension Remove the bundled GNOME Shell extension for the invoking user
  -h, --help               Show this help

Environment:
  INSTALL_DIR  Default: /opt/autospace
  BIN_DIR      Default: /usr/local/bin
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remove-config)
      REMOVE_CONFIG=1
      shift
      ;;
    --remove-gnome-extension)
      REMOVE_GNOME_EXTENSION=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

run_as_root() {
  if [[ "${EUID}" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

target_user() {
  if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    printf '%s\n' "${SUDO_USER}"
  else
    id -un
  fi
}

target_home() {
  local user
  user="$(target_user)"
  getent passwd "${user}" | cut -d: -f6
}

echo "Uninstalling ${APP_NAME}"

run_as_root rm -f "${BIN_DIR}/${APP_NAME}"
run_as_root rm -rf "${INSTALL_DIR}"

if [[ "${REMOVE_CONFIG}" -eq 1 ]]; then
  config_dir="$(target_home)/.config/${APP_NAME}"
  echo "Removing config directory ${config_dir}"
  rm -rf "${config_dir}"
fi

if [[ "${REMOVE_GNOME_EXTENSION}" -eq 1 ]]; then
  extension_dir="$(target_home)/.local/share/gnome-shell/extensions/autospace@local"
  echo "Removing GNOME Shell extension ${extension_dir}"
  if command -v gnome-extensions >/dev/null 2>&1; then
    gnome-extensions disable autospace@local || true
  fi
  rm -rf "${extension_dir}"
fi

echo "Uninstalled ${APP_NAME}"
