# Huawei Band 9 — Independent BLE Acquisition

An independent, account-free data-acquisition project for the **Huawei Band 9
(KIM-B19)**. The final runtime target is a Linux host with a Bluetooth adapter.
Huawei Health and the Android phone are used only as a temporary reference
implementation during reverse engineering.

## Status at a glance

| Capability | Status | Evidence |
|---|---|---|
| Device/firmware identified | **Verified** | `Kimi-B19FB`, firmware `4.2.0.230(C00M07)`, proprietary device-info |
| Discover Band 9 | **Verified** | `band9 scan`, `band9 endpoints` |
| Enumerate GATT | **Verified** | `band9 gatt`, `captures/gatt/` |
| Standard HRS heart rate | **Verified** | 213 packets / 212 s, ~1 Hz, screen off |
| Timestamped storage (SQLite/JSONL/CSV) | **Verified** | unit tests + live captures |
| Reconnect after BLE drop | **Verified** | monitor reconnect loop |
| HR without Huawei account | **Verified** | no pairing/bonding used |
| HR with band screen off | **Verified** | 1.17 s max gap over 212 s |
| HR after reboot / charging | **Restart requires exiting broadcast** | auto-resume untested; manual re-enable likely |
| Proprietary FE86 authentication | **HiChain3 handshake captured** | authVersion 1, deviceSupportType 4; reimplementation pending |
| Real-time HR via FE86 (`0x19`) | **Hypothesis** | Huawhoop/Band 10 evidence; not seen on Band 9 yet |
| SpO₂, HRV, stress, sleep, steps | **Partial** | automatic SpO₂ on/off confirmed; data paths not yet decoded |
| Configurable aggressive intervals | **Confirmed absent in Huawei Health** | on-device capture: only on/off and alert thresholds |
| Firmware modification | **Low feasibility** | Apollo3 secure boot, signed OTA, glued case, no recovery; see `docs/14_firmware_feasibility.md` |

> The minimum success criterion is already met: a locally running Python
> application receives timestamped heart rate from the Band 9 with no Huawei
> Health and no Huawei account.

## The important endpoint distinction

The Band 9 exposes **two different BLE identities**:

| Mode | Advertising name | Service | Address | Auth needed |
|---|---|---|---|---|
| Normal | `HUAWEI Band 9-XXX` | Huawei FE86 | one address | yes, for FE86 |
| HR Data Broadcast | `HUAWEI Band HR-XXX` | standard 0x180D + FE86 | a different address | no for 0x2A37 |

The HR broadcast address is **not** the normal address. Always discover by name
or service UUID; do not hard-code a MAC.

## Quick start

Requirements: Linux, BlueZ, Python 3.11+, a powered Bluetooth adapter.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

band9 doctor                        # adapter + endpoint check
band9 endpoints                     # show Band 9 endpoints
band9 gatt --endpoint hr_broadcast --subscribe 10
band9 hr --duration 60              # store HR in data/band9.sqlite3
```

On the band, start **Settings → HR Data Broadcasts** and keep the screen awake
for the initial connection. Once streaming, the display may turn off; the
broadcast continues (verified for 3.5 minutes; long-soak test pending).

If the band is connected to a phone, turn the phone's Bluetooth off. The Band 9
normally accepts one active BLE link on the normal endpoint.

### Useful commands

```bash
band9 scan --json captures/gatt/scan.json
band9 gatt --address <ADDR> --out captures/gatt/gatt.json
band9 hr --duration 0 --jsonl captures/raw/hr.jsonl --db data/band9.sqlite3
band9 probe-link --address <ADDR> --yes   # read-only LinkParams handshake
band9 summary --db data/band9.sqlite3
band9 export --db data/band9.sqlite3 --csv data/hr.csv --metric heart_rate
python -m pytest -q
```

## 24×7 acquisition service

The repository now also contains a production-oriented acquisition daemon,
separate dashboard and separate analysis tool. They are independent: stopping
the dashboard never stops acquisition.

```bash
pip install -e '.[api,analysis]'
PYTHON="$(command -v python)" \
  bash services/install-user-services.sh
```

- Daemon: `~/.config/systemd/user/huawei-acquisition.service`
- Dashboard: <http://127.0.0.1:8787>
- Database: `~/.local/share/band9/acquisition.sqlite3`
- Analysis: `band9-analyze --db ~/.local/share/band9/acquisition.sqlite3 --out reports/analysis`

The dashboard also includes a read-only **Statistical analytics** section:
summary cards; hourly and daily tables; HR distribution (histogram, ECDF, box,
P05–P95 bands); configurable HR bands; sleep statistics from manual
annotations; a circadian heatmap; and provisional rolling baselines. It uses the
same database without changing acquisition or raw observations. See
`docs/21_statistical_analytics.md`.

Both units are enabled and lingering is enabled, so they start at boot without
an interactive login. The daemon retries with exponential backoff until
**Settings → HR Data Broadcasts** is started on the band. See
`docs/17_acquisition_system.md` for the schema, reliability design, web controls,
sleep annotations, analysis definitions and the controlled HR-broadcast
interference experiment.

## Data model

Measurements are normalised before storage:

```
(ts_utc, metric, value, unit, source, quality, raw_hex, meta_json)
```

Examples: `heart_rate` / `bpm` / `ble_hrs`; future `spo2` / `percent`,
`rr_interval` / `ms`, `steps` / `count`, `skin_temperature` / `°C`.

Raw BLE packets are preserved in `raw_packets` and in JSONL captures. The
SQLite database and raw captures are gitignored because they contain device
identifiers and personal physiological data.

## Repository layout

```
src/fitness_band/
  acquisition/        HRS daemon, reconnect, sessions, state, spool
  api/                read-only FastAPI dashboard + analytics API
  analysis/           quality, baseline, sleep, distribution, bands,
                      heatmap, rolling baselines, report CLI
  ble_scanner.py      discovery / advertisement records
  gatt_inspector.py   read-only GATT enumeration + notifications
  protocol.py         LPv2/Huawei frame + TLV codec
  authentication.py   LinkParams probe (full HiChain work in progress)
  heart_rate.py       standard-HRS acquisition with reconnect
  device_manager.py   endpoint resolution / connection helpers
  storage.py          SQLite + CSV/JSONL
  main.py             CLI
services/             systemd user units + installer
capabilities/         machine-readable capability matrix
docs/                 research, GATT, protocol, architecture, analytics
captures/             sanitised reports; raw data stays local
tests/                protocol, acquisition, API and analytics tests
```

## Safety and privacy

- No arbitrary writes during reconnaissance. The only write is the documented
  LinkParams handshake, guarded by `--yes`.
- No pairing, bonding, factory reset or firmware flashing is performed without
  explicit consent.
- Never commit MAC addresses, auth keys, serial numbers or raw personal data.
- No claim of support is made for a command that has not been exercised against
  the physical device.
- See `SECURITY.md` for private vulnerability reporting and the full data policy.

## Public data policy

Issues, pull requests, discussions, test fixtures and documentation must not
contain MAC addresses, BLE identity addresses, serial numbers, device/account
IDs, pairing or session keys, `secret_key`/`returnCodeMac` values, raw health
records, or unredacted packet captures. Use synthetic addresses such as
`AA:BB:CC:DD:EE:FF` and aggregate, non-identifying metrics.

## Contributing

See `CONTRIBUTING.md` for setup, tests, style, privacy and hardware-safety
rules, and `CODE_OF_CONDUCT.md` for participation expectations. The short
version: run the test suite, keep analytics read-only with respect to
acquisition records, and never add raw captures or personal data.

## Security

Please report vulnerabilities privately via GitHub's **Security → Report a
vulnerability** flow. Do not open a public issue containing sensitive data.
See `SECURITY.md`.

## Medical disclaimer

This is an independent interoperability and data-acquisition project, not a
medical device. It is not affiliated with Huawei. Heart rate, sleep, SpO₂,
HRV-related and other metrics are exploratory; they are not intended for
diagnosis, treatment, or clinical decision-making. Use the software and any
hardware experiments at your own risk.

## License

MIT. See `LICENSE`.

## References

See `docs/01_research_report.md` for the full literature and source review.
Primary references: Gadgetbridge Huawei backend, Huawhoop (Band 10), Huawei
Health 11.0.0.517 static analysis, `huawei-lpv2`, and the 2019 SBA Research
Huawei Health reversing work.
