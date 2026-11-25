# Contributing

Thanks for considering a contribution. This project is an independent,
account-free BLE acquisition and analysis toolkit for the Huawei Band 9.

## Scope

Good contributions include:

- BLE/GATT protocol corrections with evidence,
- acquisition reliability and reconnect improvements,
- read-only statistical/analytics improvements,
- documentation, tests, and privacy/security hardening,
- packaging and Linux/systemd usability.

Please avoid:

- firmware flashing, bootloader/INFO0 changes, or signature bypasses,
- extracting account-bound credentials or keys,
- adding raw health data, MAC addresses, device IDs, or packet captures,
- medical claims or clinical advice.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[api,analysis,dev]'
```

Run the checks before opening a PR:

```bash
python -m pytest -q
ruff check src tests
```

For dashboard changes, also extract the inline scripts and run a JavaScript
syntax check:

```bash
python - <<'PY'
from pathlib import Path
from fitness_band.api.templates import DASHBOARD_HTML
for i, part in enumerate(DASHBOARD_HTML.split("<script>")[1:], 1):
    Path(f"/tmp/dashboard_{i}.js").write_text(part.split("</script>", 1)[0])
PY
for f in /tmp/dashboard_*.js; do node --check "$f"; done
```

## Data and privacy

- Use synthetic addresses and values in tests (`AA:BB:CC:DD:EE:FF`).
- Do not commit `data/`, `reports/`, `captures/raw/`, `captures/live/`,
  `captures/android/`, databases, or raw logs.
- Redact MACs, names with real suffixes, serial numbers, account IDs,
  session/auth keys, and health records.
- Preserve the capture policy in `captures/README.md`.

## Hardware safety

- Do not run destructive hardware operations against a device you do not own.
- Do not add code that flashes firmware, erases storage, writes INFO0, or
  modifies a bootloader.
- Prefer read-only probes and guard any write with explicit confirmation.
- Do not claim support for a command that has not been exercised on hardware.

## Pull requests

Please include:

- what changed and why,
- tests for new calculations/parsers,
- privacy impact (especially for logs, captures, addresses, and health data),
- any hardware validation performed (model/firmware, redacted host details),
- documentation updates for new metrics, commands, or limitations.

By contributing, you agree that your contribution is licensed under the
repository's MIT license and that you will follow the Code of Conduct.
