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
| HR after reboot / charging | **Not yet verified** | experiment pending |
| Proprietary FE86 authentication | **HiChain3 handshake captured** | authVersion 1, deviceSupportType 4; reimplementation pending |
| Real-time HR via FE86 (`0x19`) | **Hypothesis** | Huawhoop/Band 10 evidence; not seen on Band 9 yet |
| SpO₂, HRV, stress, sleep, steps | **Partial** | automatic SpO₂ on/off confirmed; data paths not yet decoded |
| Configurable aggressive intervals | **Confirmed absent in Huawei Health** | on-device capture: only on/off and alert thresholds |
| Firmware modification | **Out of scope for now** | see `docs/08_firmware_investigation.md` |

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
conda activate band9          # or any Python 3.11+ env
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
  ble_scanner.py      discovery / advertisement records
  gatt_inspector.py   read-only GATT enumeration + notifications
  protocol.py         LPv2/Huawei frame + TLV codec
  authentication.py   LinkParams probe (full HiChain work in progress)
  heart_rate.py       standard-HRS acquisition with reconnect
  device_manager.py   endpoint resolution / connection helpers
  storage.py          SQLite + CSV/JSONL
  main.py             CLI
docs/                 research, GATT, protocol, architecture, roadmap
captures/             sanitised reports; raw data stays local
tests/                packet-decoding and storage tests
```

## Safety and privacy

- No arbitrary writes during reconnaissance. The only write is the documented
  LinkParams handshake, guarded by `--yes`.
- No pairing, bonding, factory reset or firmware flashing is performed without
  explicit consent.
- Never commit MAC addresses, auth keys, serial numbers or raw personal data.
- No claim of support is made for a command that has not been exercised against
  the physical device.

## References

See `docs/01_research_report.md` for the full literature and source review.
Primary references: Gadgetbridge Huawei backend, Huawhoop (Band 10), Huawei
Health 11.0.0.517 static analysis, `huawei-lpv2`, and the 2019 SBA Research
Huawei Health reversing work.
