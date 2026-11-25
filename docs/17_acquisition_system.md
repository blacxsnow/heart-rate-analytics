# 17 — Continuous Acquisition and Longitudinal Analysis

This document covers the production acquisition service, the separate web
dashboard, the read-only analysis application, the database contract, the
systemd deployment, and the validation performed on 2026-11-25.

---

## 1. Two independent applications

```
                 BLE HRS (0x180D / 0x2A37)
                          │
                 acquisition daemon  ──────────────►  SQLite (WAL)
                 (systemd user unit)                  raw_measurements
                          │                           monitoring_sessions
                          │ state.json               device_events
                          │ control.json              annotations
                          ▼
                 FastAPI dashboard (separate unit, read-only + annotations)
                          │
                          ▼
                 analysis CLI (read-only; no BLE imports)
```

- **Acquisition** owns the adapter and the database writer. It never needs the
  browser or the analysis code.
- **Dashboard** reads state/DB, writes annotations and a control file. It never
  opens the BLE adapter.
- **Analysis** opens SQLite read-only and cannot modify observations.

The standard HRS path is the verified one: one notification per second,
uint8 BPM, contact bit, no RR intervals. The daemon does not use Huawei Health,
the phone, or the proprietary FE86 channel.

## 2. Database contract

Created at `~/.local/share/band9/acquisition.sqlite3` (override with
`BAND9_DB`). WAL, `synchronous=NORMAL`, foreign keys, 5 s busy timeout.

| Table | Purpose |
|---|---|
| `raw_measurements` | append-only observations: UTC timestamp, receive timestamp, monotonic time, BPM, device, session, source, raw payload, quality flags, timezone, `measurement_time_known`, epoch |
| `monitoring_sessions` | daemon run: start/end, status, totals, expected/actual intervals, disconnect count, metadata |
| `device_events` | connected/disconnected, monitoring started/paused/stopped, process start/stop, session interrupted, adapter unavailable, scan miss, reconnect/error events |
| `annotations` | manual sleep/event intervals with confidence and notes |

`raw_measurements` is never updated by the acquisition process. Missing data is
not inserted. Repeated BPM values are preserved.

## 3. Timestamp semantics

The HRS notification carries no measurement timestamp. Therefore:

- `timestamp_utc` and `received_at_utc` are the PC reception time.
- `measurement_time_known = 0` and quality flags say
  `time_source = "pc_reception"`.
- `monotonic_timestamp` is the host monotonic clock, useful for interval checks.
- `tz_offset_minutes` records the local offset at reception.

The system never claims that PC reception equals sensor acquisition time.

## 4. Reliability design

- **Reconnect:** exponential backoff (2 s → 60 s) with jitter; reset after a
  stable connection (≥ 15 s or data).
- **Watchdog:** if no notification arrives for 15 s on a connected link, the
  daemon disconnects and reconnects.
- **Adapter failure:** scan errors are recorded as `adapter_unavailable`; the
  loop keeps retrying.
- **Crash/reboot:** systemd `Restart=always`; open sessions are marked
  `interrupted` with an event on the next start.
- **Database failure:** the observation is appended to a disk spool
  (`spool/pending-YYYY-MM-DD.jsonl`) and drained at startup/every 60 s.
- **Web failure:** the daemon and systemd units are independent; closing the
  browser or stopping the web unit does not affect acquisition.
- **Control:** the daemon polls `control.json`; the web writes it atomically.
  Start/connect/reconnect unpause and bump a reconnect counter; stop/disconnect
  pause.
- **Logging:** JSON lines to stdout/journald.

## 5. Deployment

```bash
pip install -e '.[api,analysis]'
PYTHON=/path/to/python bash services/install-user-services.sh
```

This installs:

- `~/.config/systemd/user/huawei-acquisition.service`
- `~/.config/systemd/user/huawei-web.service`
- enables lingering so both start at boot without a login session.

Dashboard: <http://127.0.0.1:8787> (loopback only by default). To expose it on
the LAN, change the web unit to `--host 0.0.0.0` and configure a firewall; the
API has no authentication, so do not expose it untrusted.

Useful commands:

```bash
systemctl --user status huawei-acquisition.service huawei-web.service
journalctl --user -u huawei-acquisition.service -f
systemctl --user restart huawei-acquisition.service
systemctl --user stop huawei-acquisition.service
```

The restart button on the dashboard is disabled by default. Enable it with
`BAND9_ALLOW_RESTART=1` in the web unit (the web process then runs
`systemctl --user restart huawei-acquisition.service`).

## 6. Dashboard

- Connection/service status, current HR, last measurement, sampling interval,
  session duration, total measurements, DB size, last connection/disconnection,
  reconnect attempts, spool depth.
- Live SVG graph for 1/5/15/60 minutes; line breaks at gaps and red bands for
  disconnection intervals.
- Start/connect/disconnect/stop/reconnect controls.
- Sleep annotation form with retrospective editing/deletion; crossing midnight
  is supported (an end at/before the start is interpreted as the next day).
- CSV export of all raw measurements.

## 7. Analysis application

```bash
band9-analyze --db ~/.local/share/band9/acquisition.sqlite3 --out reports/analysis
python -m fitness_band.analysis --db ... --out ...
```

Outputs `quality.json`, `baseline.json`, `sleep.json`, `circadian.json`,
`dynamics.json`, `longitudinal.json`, `sessions.json`, `daily.csv`,
`summary.md`, and PNG figures.

Definitions and guardrails:

- Missing intervals are reported, never zero-filled/interpolated.
- Resting HR is an **observed low-activity proxy** (lower decile of 10-min
  medians) because activity data is unavailable; it is labelled accordingly.
- Sleep HR uses manual sleep annotations only; no REM/awakening inference.
- `dynamics` reports BPM variation and elevated episodes; it explicitly does
  **not** compute RMSSD/SDNN/pNN50 from the 1 Hz BPM stream.
- The first 28 days are a personal empirical baseline, not a clinical range.

## 8. Validation performed

| Check | Result |
|---|---|
| Unit + integration tests | **71 passed** (database, API, spool, timestamps, parser, analysis, simulation) |
| End-to-end simulation (60 s) | DB rows, live status, HR graph data, CSV export, analysis report and PNGs produced |
| Sleep annotation API | create/read/delete; overnight interval normalised |
| Control file | start/stop/reconnect actions written atomically |
| Process crash | `kill -9` on the daemon: systemd restarted it in ~5 s; old session marked `interrupted`; new session started |
| Web independence | web unit stayed up while acquisition restarted |
| Boot persistence | user units enabled and lingering enabled (`Linger=yes`) |
| Real reboot | **not performed** (would disrupt the host); verify once at a convenient time with `last reboot` + dashboard continuity |
| Real BLE acquisition | band was charging / HR broadcast off during deployment; daemon is retrying with backoff and will connect when the broadcast starts |

## 9. HR broadcast vs background metrics experiment

This is a separate controlled experiment; do not assume interference.

### Phases

- **A — baseline:** HR broadcast off, normal wear, 48 h. Sync Huawei Health
  daily and record the historical HR/sleep/SpO₂ availability and battery.
- **B — broadcast on:** HR broadcast on, PC daemon connected continuously,
  48 h. Record the same endpoints and battery.
- **C — broadcast on, phone app disconnected:** broadcast on, PC daemon
  connected, Huawei Health force-stopped/no phone sync, 48 h.

### Observations to record

- Does the band's internal historical HR still accumulate? Compare the band's
  own history screen/Health sync before and after each phase.
- Do sleep metrics, automatic SpO₂, stress and other metrics still appear?
- Battery percentage and discharge rate per 24 h.
- Gaps in the PC HRS stream versus gaps in the band's internal history.

### Interpretation rule

If broadcasting stops internal storage, the PC database is the authoritative
HR record for phases B/C. If internal storage continues, the two records can be
cross-checked. Do not infer an effect from a single short session.

## 10. First-run checklist (after charging)

1. On the band: **Settings → HR Data Broadcasts → start**.
2. Ensure the band is not connected to the phone for the normal endpoint; the
   HR broadcast endpoint is separate and account-free.
3. `systemctl --user status huawei-acquisition.service` should show
   `connected` and `band9` state should show a current HR.
4. Open <http://127.0.0.1:8787>; verify live points and sampling ≈ 1 s.
5. Add a sleep annotation for the previous night.
6. Leave it running; after several days run `band9-analyze`.
