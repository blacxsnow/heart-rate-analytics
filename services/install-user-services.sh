#!/usr/bin/env bash
# Install and start the two user services for the current repository.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$(command -v python3)}"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
DATA_DIR="${BAND9_DATA_DIR:-$HOME/.local/share/band9}"

mkdir -p "$UNIT_DIR" "$DATA_DIR"

for unit in huawei-acquisition huawei-web; do
  sed -e "s|@REPO@|$REPO|g" -e "s|@PYTHON@|$PYTHON|g" \
    "$REPO/services/$unit.service.in" > "$UNIT_DIR/$unit.service"
  echo "installed $UNIT_DIR/$unit.service"
done

systemctl --user daemon-reload
systemctl --user enable huawei-acquisition.service huawei-web.service

if [[ "${BAND9_NO_START:-0}" == "1" ]]; then
  echo "services enabled; not started (BAND9_NO_START=1)"
else
  # Restart so a rerun of the installer picks up new code.
  systemctl --user restart huawei-acquisition.service huawei-web.service
fi

if loginctl enable-linger "$USER" 2>/dev/null; then
  echo "lingering enabled for $USER (services start at boot without login)"
else
  echo "warning: could not enable lingering; run: sudo loginctl enable-linger $USER"
fi

systemctl --user --no-pager --lines=5 status huawei-acquisition.service || true
systemctl --user --no-pager --lines=5 status huawei-web.service || true
echo
echo "Dashboard: http://127.0.0.1:8787"
echo "Data:      $DATA_DIR"
