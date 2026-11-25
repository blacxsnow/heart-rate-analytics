#!/usr/bin/env bash
# Pull the active Android Bluetooth HCI snoop log and record metadata.
#
# Usage: scripts/pull_hci_log.sh [output.btsnoop]
set -euo pipefail

OUT="${1:-captures/android/hci_$(date +%Y%m%d_%H%M%S).btsnoop}"
mkdir -p "$(dirname "$OUT")"

LATEST="$(adb shell su -c 'ls -t /data/misc/bluetooth/logs/*.log | head -1' | tr -d '\r')"
if [ -z "$LATEST" ]; then
  echo "No HCI log found. Enable Bluetooth HCI snoop logging first." >&2
  exit 1
fi

echo "Pulling $LATEST -> $OUT"
adb exec-out su -c "cat '$LATEST'" > "$OUT"
ls -lh "$OUT"

META="${OUT%.btsnoop}.json"
python3 - "$OUT" "$LATEST" "$META" <<'PY'
import json, os, sys, time, hashlib
out, remote, meta = sys.argv[1], sys.argv[2], sys.argv[3]
h = hashlib.sha256()
with open(out, "rb") as fh:
    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
        h.update(chunk)
payload = {
    "captured_at": time.time(),
    "captured_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "remote_path": remote,
    "local_path": out,
    "size": os.path.getsize(out),
    "sha256": h.hexdigest(),
}
with open(meta, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2, sort_keys=True)
print(json.dumps(payload, indent=2))
PY
