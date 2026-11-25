# Capture Policy

This directory contains **sanitised reports only**.

- `gatt/` — GATT maps and device-info samples with addresses removed.
- `android/` — (local, gitignored) btsnoop logs and Frida output.
- `raw/` — (local, gitignored) per-session JSONL, including MACs and raw
  physiological data.
- `live/` — (local, gitignored) long-running soak captures.

Rules:

1. Never commit a MAC address, serial number, auth key, account ID or raw
   personal health record.
2. Keep the original raw capture locally; publish only the redacted extract.
3. Record the device model, firmware (if known), host adapter, BlueZ version and
   timestamp with every capture.
4. Do not edit a capture in place. Create a derived, redacted copy.
5. Preserve failed captures too; they are evidence of what does not work.
