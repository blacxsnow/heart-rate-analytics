#!/usr/bin/env bash
# Attach Frida to a running Huawei Health process and log BLE hooks.
set -euo pipefail
OUT="${1:-captures/android/frida_$(date +%Y%m%d_%H%M%S).log}"
mkdir -p "$(dirname "$OUT")"

if ! adb shell su -c 'ps -A | grep -q frida-server'; then
  echo "Starting frida-server..."
  adb shell su -c '/data/local/tmp/frida-server -D'
  sleep 2
fi

echo "Writing $OUT"
frida -U -n "Huawei Health" -l scripts/frida_ble_hooks.js -o "$OUT"
