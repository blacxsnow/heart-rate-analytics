#!/usr/bin/env bash
# One-command installer for the Band 9 acquisition + analytics dashboard.
#
# Defaults:
#   - create/use <repo>/.venv
#   - install the api + analysis extras
#   - install, enable and (re)start the user services
#   - enable lingering so the services start at boot without a login
#
# No sudo is used. System packages (BlueZ, Python venv support) must already
# be installed; the script prints distro-specific hints if they are missing.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
VENV_DIR="${BAND9_VENV:-$REPO/.venv}"
USE_VENV=1
INSTALL_SERVICES=1
START_SERVICES=1
CHECK_ONLY=0
DATA_DIR="${BAND9_DATA_DIR:-$HOME/.local/share/band9}"

usage() {
  cat <<'EOF'
Usage: ./install.sh [options]

Options:
  --python PATH       Base interpreter for the venv (default: python3)
  --venv PATH         Venv location (default: <repo>/.venv)
  --no-venv           Install into the selected interpreter instead of a venv
  --no-services       Do not install systemd user units
  --no-start          Install/enable units but do not start them now
  --check             Check prerequisites and print the plan; change nothing
  -h, --help          Show this help

Examples:
  ./install.sh
  ./install.sh --check
  ./install.sh --no-services
  ./install.sh --python /usr/bin/python3.12

Environment:
  PYTHON              Default interpreter (same as --python)
  BAND9_VENV          Default venv location
  BAND9_DATA_DIR      Data directory (default: ~/.local/share/band9)
EOF
}

log()  { printf '\n==> %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
fail() { printf 'error: %s\n' "$*" >&2; exit 1; }

while (($#)); do
  case "$1" in
    --python)
      [[ $# -ge 2 ]] || fail "--python requires a path"
      PYTHON_BIN="$2"
      shift 2
      ;;
    --venv)
      [[ $# -ge 2 ]] || fail "--venv requires a path"
      VENV_DIR="$2"
      shift 2
      ;;
    --no-venv)
      USE_VENV=0
      shift
      ;;
    --no-services)
      INSTALL_SERVICES=0
      shift
      ;;
    --no-start)
      START_SERVICES=0
      shift
      ;;
    --check)
      CHECK_ONLY=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown option: $1 (use --help)"
      ;;
  esac
done

trap 'printf "\nInstall failed near line %s.\n" "$LINENO" >&2' ERR

[[ "$(uname -s)" == "Linux" ]] || fail "this installer targets Linux"
[[ "$(id -u)" != "0" ]] || fail "run as your normal user, not root (user services/lingering)"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  fail "Python not found: $PYTHON_BIN"
fi
"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
  || fail "Python 3.11+ is required (found $("$PYTHON_BIN" --version 2>&1))"

if [[ $USE_VENV -eq 1 ]]; then
  VENV_PY="$VENV_DIR/bin/python"
else
  VENV_PY="$PYTHON_BIN"
fi

BLUETOOTH_OK=1
if ! command -v bluetoothctl >/dev/null 2>&1; then
  BLUETOOTH_OK=0
fi

SYSTEMD_OK=1
if ! systemctl --user show-environment >/dev/null 2>&1; then
  SYSTEMD_OK=0
fi
if [[ $SYSTEMD_OK -eq 0 && $INSTALL_SERVICES -eq 1 ]]; then
  warn "systemd --user is not available; services will not be installed"
  INSTALL_SERVICES=0
fi

if [[ $CHECK_ONLY -eq 1 ]]; then
  log "Installation check (no changes made)"
  echo "Repository:        $REPO"
  echo "Base Python:       $PYTHON_BIN ($("$PYTHON_BIN" --version 2>&1))"
  if [[ $USE_VENV -eq 1 ]]; then
    echo "Venv:              $VENV_DIR"
    [[ -x "$VENV_PY" ]] && echo "Existing venv:     yes" || echo "Existing venv:     no (will be created)"
  else
    echo "Venv:              disabled; using $PYTHON_BIN"
  fi
  echo "Data directory:    $DATA_DIR"
  [[ $BLUETOOTH_OK -eq 1 ]] && echo "bluetoothctl:      found" || echo "bluetoothctl:      MISSING"
  [[ $SYSTEMD_OK -eq 1 ]] && echo "systemd --user:    available" || echo "systemd --user:    unavailable"
  [[ $INSTALL_SERVICES -eq 1 ]] && echo "Services:          will install/enable" || echo "Services:          disabled"
  [[ $START_SERVICES -eq 1 ]] && echo "Start now:         yes" || echo "Start now:         no"
  if [[ $BLUETOOTH_OK -eq 0 ]]; then
    echo
    echo "Install BlueZ first:"
    echo "  Fedora:  sudo dnf install bluez bluez-tools"
    echo "  Debian:  sudo apt install bluez"
    echo "  Arch:    sudo pacman -S bluez bluez-utils"
  fi
  echo
  echo "Run ./install.sh without --check to perform the installation."
  exit 0
fi

if [[ $USE_VENV -eq 1 ]]; then
  if [[ ! -x "$VENV_PY" ]]; then
    log "Creating virtual environment at $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR" \
      || fail "could not create the venv; install python3-venv/ensurepip (Debian/Ubuntu: sudo apt install python3-venv)"
  fi
  [[ -x "$VENV_PY" ]] || fail "venv Python not found: $VENV_PY"
else
  log "Using the selected interpreter directly: $PYTHON_BIN"
fi

"$VENV_PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
  || fail "the selected interpreter is older than Python 3.11"

log "Installing Python packages (api + analysis)"
( cd "$REPO" && "$VENV_PY" -m pip install -e '.[api,analysis]' ) \
  || fail "pip installation failed"

"$VENV_PY" -c 'import fastapi, pandas, uvicorn' \
  || fail "Python dependencies are incomplete after installation"

mkdir -p "$DATA_DIR"

if [[ $INSTALL_SERVICES -eq 1 ]]; then
  log "Installing systemd user services"
  PYTHON="$VENV_PY" \
  BAND9_NO_START="$((1 - START_SERVICES))" \
  BAND9_DATA_DIR="$DATA_DIR" \
    bash "$REPO/services/install-user-services.sh"
else
  log "Skipping systemd user services (--no-services)"
fi

if [[ $BLUETOOTH_OK -eq 0 ]]; then
  warn "bluetoothctl was not found; install BlueZ before starting acquisition:"
  warn "  Fedora: sudo dnf install bluez bluez-tools"
  warn "  Debian: sudo apt install bluez"
  warn "  Arch:   sudo pacman -S bluez bluez-utils"
fi

log "Installation complete"
if [[ $USE_VENV -eq 1 ]]; then
  ACTIVATE_HINT="source \"$VENV_DIR/bin/activate\""
else
  ACTIVATE_HINT="(no venv; use $PYTHON_BIN directly)"
fi
cat <<EOF
Repository:  $REPO
Interpreter: $VENV_PY
Data:        $DATA_DIR
Dashboard:   http://127.0.0.1:8787

Next steps:
  1. On the band: Settings -> HR Data Broadcasts -> start.
  2. Open the dashboard and confirm connection_status = connected.
  3. Optional: $ACTIVATE_HINT
  4. Analysis:
       "$VENV_PY" -m fitness_band.analysis --db "$DATA_DIR/acquisition.sqlite3" --out reports/analysis
     or, after activation, band9-analyze.

Service commands:
  systemctl --user status huawei-acquisition.service huawei-web.service
  systemctl --user restart huawei-acquisition.service
  journalctl --user -u huawei-acquisition.service -f
EOF

if [[ $INSTALL_SERVICES -eq 1 && $START_SERVICES -eq 1 ]]; then
  systemctl --user --no-pager --lines=3 status huawei-acquisition.service || true
  systemctl --user --no-pager --lines=3 status huawei-web.service || true
fi
