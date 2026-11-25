#!/usr/bin/env bash
# Pull the active Android Bluetooth HCI snoop log (btsnoop) and its GATT event
# records, then record metadata.
#
# Android stores the real btsnoop capture in:
#   /data/misc/bluetooth/cached_hci/btsnoop_hci_*.cfa
# The /data/misc/bluetooth/logs/*.log files are Bluetooth stack text logs, not
# btsnoop, and are not used here.
#
# Usage: scripts/pull_hci_log.sh [output.btsnoop]
set -euo pipefail

OUT="${1:-captures/android/hci_$(date +%Y%m%d_%H%M%S).btsnoop}"
mkdir -p "$(dirname "$OUT")"

LATEST="$(adb shell su -c 'ls -t /data/misc/bluetooth/cached_hci/btsnoop_hci_*.cfa | head -1' | tr -d '\r')"
if [ -z "$LATEST" ]; then
  echo "No btsnoop HCI file found. Is Bluetooth HCI snoop logging enabled?" >&2
  exit 1
fi

echo "Pulling $LATEST -> $OUT"
adb exec-out su -c "cat '$LATEST'" > "$OUT"
ls -lh "$OUT"

# Matching GATT event record (human-readable) is useful for correlating scans
# and service discovery with the binary capture.
BASE="$(basename "$LATEST" .cfa)"
GATT_EVENT="/data/misc/bluetooth/cached_hci/${BASE/btsnoop_hci_/event_record_gatt_}.txt"
EVENT="/data/misc/bluetooth/cached_hci/${BASE/btsnoop_hci_/event_record_}.txt"
for extra in "$GATT_EVENT" "$EVENT"; do
  if adb shell su -c "[ -f '$extra' ]" >/dev/null 2>&1; then
    dest="${OUT%.btsnoop}_$(basename "$extra")"
    adb exec-out su -c "cat '$extra'" > "$dest"
    echo "Pulled $extra -> $dest"
  fi
done

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
