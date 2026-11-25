# Huawei Band 9 — Independent Acquisition and Statistical Analysis

An independent, account-free project for the **Huawei Band 9 (KIM-B19)** with
two equally important parts: a 24×7 BLE heart-rate acquisition service and a
separate read-only statistical analysis application. The final runtime target is
a Linux host with a Bluetooth adapter. Huawei Health and the Android phone are
used only as a temporary reference implementation during reverse engineering.

Repository: <https://github.com/blacxsnow/heart-rate-analytics>

## Two independent applications

| Application | Owns | Never does |
|---|---|---|
| **Acquisition** | BLE adapter, HRS stream, reconnect/watchdog, sessions, raw SQLite writes, live dashboard | statistical inference, raw-record edits |
| **Analysis** | read-only SQLite access, descriptive/longitudinal statistics, analytics UI, report CLI | BLE connections, acquisition writes, raw-record edits |

The boundary is deliberate: stopping the dashboard or analysis never stops
acquisition; the analysis process has no BLE imports and opens SQLite with
`mode=ro`.

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
| Statistical summary + hourly/daily tables | **Implemented and tested** | read-only analytics dashboard, `docs/21_statistical_analytics.md` |
| HR distribution + configurable bands | **Implemented and tested** | histogram, ECDF, box, P05–P95, band episodes |
| Sleep, circadian heatmap, rolling baselines | **Implemented and tested** | manual sleep annotations, date×hour heatmap, provisional baselines |
| Read-only analysis boundary | **Verified** | SQLite `mode=ro`; analysis has no BLE imports; raw records append-only |
| Firmware modification | **Low feasibility** | Apollo3 secure boot, signed OTA, glued case, no recovery; see `docs/14_firmware_feasibility.md` |

> The minimum success criterion is already met: a locally running Python
> application receives timestamped heart rate from the Band 9 with no Huawei
> Health and no Huawei account.
>
> The analysis criterion is met too: a separate read-only application produces
> descriptive, distribution, sleep, circadian and longitudinal statistics from
> that database without opening the BLE adapter or modifying raw observations.

## The important endpoint distinction

The Band 9 exposes **two different BLE identities**:

| Mode | Advertising name | Service | Address | Auth needed |
|---|---|---|---|---|
| Normal | `HUAWEI Band 9-XXX` | Huawei FE86 | one address | yes, for FE86 |
| HR Data Broadcast | `HUAWEI Band HR-XXX` | standard 0x180D + FE86 | a different address | no for 0x2A37 |

The HR broadcast address is **not** the normal address. Always discover by name
or service UUID; do not hard-code a MAC.

## Install

The recommended setup is one user-level command:

```bash
./install.sh
```

It creates `.venv`, installs the API + analysis extras, installs and enables the
systemd user units, and starts the dashboard. It does not use `sudo`, pair or
flash the band, or modify raw data. See **[INSTALL.md](INSTALL.md)** for
prerequisites, options (`--check`, `--no-services`, `--no-start`, `--no-venv`),
service management, analysis, updates, uninstall and troubleshooting.

```bash
./install.sh --check       # inspect prerequisites without changing anything
```

## Manual install and CLI quick start

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

## Statistical analysis

The analysis side is a first-class application, not a reporting afterthought. It
has its own read-only dashboard sections and a separate CLI, and it treats the
acquisition database as immutable input.

```
BLE HRS ──► acquisition daemon ──► SQLite (WAL, append-only raw_measurements)
                                      │
                                      ├── live acquisition dashboard
                                      ├── read-only analytics section
                                      └── band9-analyze (JSON/CSV/Markdown/PNG)
```

### Statistical ranges

| Range | Meaning |
|---|---|
| Current session | Latest monitoring session start → now/session end |
| Last 1 / 6 / 12 / 24 hours | Rolling window ending now |
| Today / Yesterday | Local calendar day (today is partial) |
| Last 7 / 28 days | Rolling window ending now |
| Custom | Explicit start/end; future end is marked partial |

All calendar grouping uses **Asia/Kolkata (IST, UTC+05:30)** by default. Hourly
rows are a specific **date + hour**, not a merge of the same clock hour across
days. Incomplete periods show the available data with an explicit warning; they
are never zero-filled or interpolated.

### Summary and aggregation

| Feature | What it reports |
|---|---|
| Summary cards | Count, mean, median, min, max, SD, MAD, IQR, P05/P95, CV, range, recording duration, coverage |
| Hourly table | Date, hour, count, mean, median, min, max, SD, MAD, IQR, P95, range, duration, coverage; sortable |
| Daily table | Date, count, mean, median, min, max, SD, MAD, IQR, P95, coverage, duration, min-at, max-at, sustained 5-minute min/max, time-weighted mean, disconnect count |
| Hourly drill-down | Click an hour to plot its raw HR trajectory with gaps preserved |

Every row/period reports its own sample count and coverage. A 24-hour range with
68 minutes of samples shows ~4.7% coverage and a warning rather than pretending
to be complete.

### Distribution and bands

| Feature | What it reports |
|---|---|
| Histogram | Fixed-width bins, selectable 2/5/10 bpm |
| ECDF | Proportion of recorded time below each BPM |
| Box plot | Q1, median, Q3, 1.5×IQR whiskers and outliers |
| Percentile bands | Hourly P05 / median / P95 |
| HR bands | Editable intervals, time-weighted duration, % of monitored time, episode count, longest episode, stacked daily bars |

The default bands are descriptive only (`<50`, `50–59`, …, `120+`). They are
not diagnostic ranges or exercise-intensity classifications unless the user
explicitly configures them for that purpose.

### Sleep, circadian patterns and baselines

| Feature | What it reports |
|---|---|
| Sleep statistics | Per annotated night: mean, median, min, max, SD, MAD, IQR, P05/P95, sustained 5-minute min/max, nadir BPM, time to nadir, nadir clock time, awake-resting proxy, sleep-vs-awake difference |
| Sleep history | One row per annotation, including annotations with no samples |
| Sleep-onset trajectory | 5-minute median HR aligned to bedtime, plus a mean trajectory across nights |
| Circadian heatmap | Date × local hour, selectable mean/median/SD/MAD/P95; empty cells are not imputed |
| Rolling baseline | 1 h, 6 h, 24 h, 7 d and 28 d rolling mean **and** median |
| Deviations | 1-hour mean minus resting/sleep baseline; robust median/MAD score; conventional z-score |
| Trend | OLS slope of daily mean HR (bpm/day) with R² |
| Provisional status | Explicitly marked until enough data exists (28 days for the full baseline) |

Sleep analysis uses **only manual sleep annotations** that overlap the selected
range. It does not infer sleep stages, REM, or awakenings from the 1 Hz BPM
stream. Awake-resting is a lower-decile proxy, not a clinical resting HR.

### Metric definitions

| Metric | Definition |
|---|---|
| SD | Sample standard deviation (`ddof=1`; 0 for n=1) |
| MAD | Median of \|xᵢ − median\| (unscaled) |
| IQR | P75 − P25 |
| P05 / P95 | Percentiles with linear interpolation |
| CV | `SD / mean × 100` |
| Recording duration | Σ `min(Δᵢ, 5 s)` over adjacent observations, plus the median interval for the last sample |
| Coverage | Recording duration ÷ period duration, clipped to 0–1 |
| Sustained 5-minute HR | Rolling 5-minute mean requiring at least 150 observations; reported min/max |
| Time-weighted mean | Observations weighted by time to the next sample, capped at 5 s |

The 1 Hz BPM stream is **not** beat-to-beat HRV. The project does not compute
RMSSD, SDNN, or pNN50 from it.

### CLI reports

```bash
band9-analyze --db ~/.local/share/band9/acquisition.sqlite3 --out reports/analysis
```

This produces `quality.json`, `baseline.json`, `sleep.json`, `circadian.json`,
`dynamics.json`, `longitudinal.json`, `sessions.json`, `daily.csv`,
`summary.md`, and PNG figures. The analysis code opens SQLite read-only and
cannot modify raw observations.

### Immediate vs longitudinal value

- **After 10 minutes:** summary cards, hourly statistics, distribution, bands,
  and the 1-hour rolling baseline.
- **After a few hours:** daily statistics, sleep rows for the previous night,
  heatmap cells, and 6/24-hour baselines.
- **After 7–28 days:** rolling medians, baseline deviations, daily trends, and
  stable longitudinal comparisons. Until then the baseline is labelled
  provisional.

The analytics section lives below the live acquisition monitor and never
changes existing acquisition controls. See `docs/21_statistical_analytics.md`
for the API contract and exact definitions.

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
install.sh            one-command user-level installer
INSTALL.md            full setup, service, update and troubleshooting guide
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
