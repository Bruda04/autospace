#!/usr/bin/env bash
set -euo pipefail

APP_NAME="autospace"
INSTALL_DIR="${INSTALL_DIR:-/opt/autospace}"
BIN_DIR="${BIN_DIR:-/usr/local/bin}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
INSTALL_EXAMPLE_CONFIG=0
INSTALL_GNOME_EXTENSION=0

usage() {
  cat <<USAGE
Usage: scripts/install.sh [options]

Installs autospace system-wide.

Options:
  --install-example-config  Copy examples/presets to ~/.config/autospace/presets
  --install-gnome-extension Install the bundled GNOME Shell extension for the invoking user
  -h, --help                Show this help

Environment:
  INSTALL_DIR  Default: /opt/autospace
  BIN_DIR      Default: /usr/local/bin
  PYTHON_BIN   Default: python3
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-example-config)
      INSTALL_EXAMPLE_CONFIG=1
      shift
      ;;
    --install-gnome-extension)
      INSTALL_GNOME_EXTENSION=1
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

copy_as_user() {
  local src="$1"
  local dst="$2"
  local user
  user="$(target_user)"
  mkdir -p "$(dirname "${dst}")"
  cp -R "${src}" "${dst}"
  if [[ "${EUID}" -eq 0 ]]; then
    chown -R "${user}:${user}" "${dst}"
  fi
}

echo "Installing ${APP_NAME} from ${SOURCE_DIR} to ${INSTALL_DIR}"

run_as_root rm -rf "${INSTALL_DIR}"
run_as_root mkdir -p "${INSTALL_DIR}"
run_as_root cp -R \
  "${SOURCE_DIR}/pyproject.toml" \
  "${SOURCE_DIR}/README.md" \
  "${SOURCE_DIR}/LICENSE" \
  "${SOURCE_DIR}/src" \
  "${SOURCE_DIR}/examples" \
  "${SOURCE_DIR}/gnome-extension" \
  "${INSTALL_DIR}/"

run_as_root "${PYTHON_BIN}" -m venv "${INSTALL_DIR}/.venv"
run_as_root "${INSTALL_DIR}/.venv/bin/pip" install --upgrade pip
run_as_root "${INSTALL_DIR}/.venv/bin/pip" install "${INSTALL_DIR}"

run_as_root mkdir -p "${BIN_DIR}"
run_as_root ln -sf "${INSTALL_DIR}/.venv/bin/${APP_NAME}" "${BIN_DIR}/${APP_NAME}"

if [[ "${INSTALL_EXAMPLE_CONFIG}" -eq 1 ]]; then
  config_dir="$(target_home)/.config/${APP_NAME}"
  echo "Installing example presets to ${config_dir}/presets"
  mkdir -p "${config_dir}/presets"
  copy_as_user "${SOURCE_DIR}/examples/presets/." "${config_dir}/presets"
fi

if [[ "${INSTALL_GNOME_EXTENSION}" -eq 1 ]]; then
  extension_dir="$(target_home)/.local/share/gnome-shell/extensions/autospace@local"
  echo "Installing GNOME Shell extension to ${extension_dir}"
  rm -rf "${extension_dir}"
  mkdir -p "$(dirname "${extension_dir}")"
  copy_as_user "${SOURCE_DIR}/gnome-extension/autospace@local" "${extension_dir}"
  if command -v gnome-extensions >/dev/null 2>&1; then
    gnome-extensions enable autospace@local || true
  fi
fi

echo "Installed ${APP_NAME}: ${BIN_DIR}/${APP_NAME}"
echo "Run: ${APP_NAME} check"
