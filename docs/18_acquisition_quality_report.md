# 18 — Acquisition Quality and Deployment Report

**Date:** 2026-11-25
**Scope:** first deployment of the 24×7 acquisition service, while the Band 9
was charging and HR broadcasting was not active.
**Real-device status:** 17 real HRS samples were captured on 2026-11-25
23:14–23:15 at ~0.99 s; the band then stopped advertising the HR-broadcast
endpoint after a manual reconnect request. The daemon remains healthy and is
retrying with exponential backoff.

---

## 1. Deployment state

| Item | Value |
|---|---|
| Acquisition unit | `huawei-acquisition.service` (user), enabled, active |
| Dashboard unit | `huawei-web.service` (user), enabled, active |
| Boot persistence | `Linger=yes`, units enabled under `default.target` |
| Database | `~/.local/share/band9/acquisition.sqlite3` |
| Dashboard | <http://127.0.0.1:8787> |
| Current real DB | 0 measurements, sessions/events only (band charging) |
| Backoff observed | 2.7 s → 4.5 s → … up to 60 s, reset after stable connection |

The daemon is intentionally independent of the dashboard. Stopping the web
unit does not stop acquisition, and the web unit stayed up while the acquisition
unit was killed and restarted.

## 2. Validation results

| Test | Result |
|---|---|
| Unit/integration suite | **92 passed** |
| Reconnect state machine | Link drop, manual reconnect, backoff cancellation, pause/resume, stale watchdog, missing endpoint, stale BlueZ link, cache removal, broadcast-off classification |
| Failure classification | Adapter powered off, adapter unavailable, stuck discovery → reset, reset control action, exception codes |
| Advertisement classification | Live `HUAWEI Band 10-TEST` normal name, HR/normal separation, address filter |
| Endurance run | 10-minute scripted run: adapter power loss, pause/resume, `SIGKILL`, web restart, forced link drop, short adapter cycles — all recovered; see `19_endurance_test.md` |
| Simulated 60 s acquisition | 72 measurements at ~0.5 s; DB/session/events/state written |
| Live dashboard API | status, HR points, CSV export, annotations all returned successfully |
| Sleep annotation | created, listed and deleted; end-before-start normalised to next day |
| Control file | start/stop/reconnect actions persisted atomically |
| Reconnect during 2 s backoff | new attempt in **0.21 s** (previously waited for the full backoff) |
| Pause / resume | paused in **1.11 s**, zero retries while paused, resumed in **0.96 s** with backoff reset to 2 s |
| Process crash | `SIGKILL` → systemd restarted; old session marked `interrupted`; new session started |
| Web independence | acquisition PID unchanged across a web restart |
| Empty real DB analysis | `band9-analyze` completed and produced a “no data” report |
| Timestamps | dashboard, chart axis and annotation input use explicit `Asia/Kolkata` (IST), independent of the browser timezone |
| Real reboot | **not performed** — requires a host reboot at a convenient time |
| Real BLE acquisition | **17 samples at ~0.99 s** earlier; later scans found the normal endpoint but no HR endpoint (broadcast off) |


## 3. Simulation quality report

The simulation is explicitly marked `source='simulated'`; it is not real
health data.

```
measurements                 72
observed interval            0.5031 s
configured interval          0.5 s
completeness                 1.0
gaps > 5 s                   0
duplicate candidates         0
sessions                     1
```

Generated artifacts (local, ignored by Git):

- `reports/demo/quality.json`
- `reports/demo/baseline.json`
- `reports/demo/dynamics.json`
- `reports/demo/longitudinal.json`
- `reports/demo/daily.csv`
- `reports/demo/summary.md`
- `overview.png`, `circadian.png`, `longitudinal.png`

The sleep annotation used for the simulation did not overlap the simulated
time range, so the sleep report correctly returned “no measurements inside
sleep intervals” rather than inventing a value.

## 4. Real database report

The first real run produced 17 measurements in session 6:

```
total measurements          17
observed interval (p50)     0.99 s
interval p05 / p95          0.83 / 3.90 s
completeness                0.607
longest gap                 11.7 s
duplicate candidates        0
```

`band9-analyze --db ~/.local/share/band9/acquisition.sqlite3 --out reports/real`
produced `quality.json`, `baseline.json`, `dynamics.json`,
`longitudinal.json`, `daily.csv` and `summary.md`; no plots were requested.
The 11.7 s gap is reported explicitly, not filled.

After the manual reconnect request, a fresh scan found no `HUAWEI Band HR-*`
endpoint and BlueZ could not find the cached address. The band was not
advertising; the service kept retrying. The current blocked condition is
therefore band-side (broadcast off / power), not a web or database failure.

### 4.1 Root cause of the “will not reconnect” loop

BlueZ still reported the HR endpoint as `Connected: yes` after the daemon had
disconnected. A connected LE peripheral does not advertise, so every scan
missed it, and the old cleanup only ran after a failed **connect** — which
could never be reached. A manual `bluetoothctl disconnect` immediately made the
band advertise again at -68 dBm with service `0x180D`.

The daemon now releases stale `HUAWEI Band HR-*` links before every scan,
removes the cache entry if the release is refused, verifies the link after
every disconnect, and re-scans. It also treats the normal endpoint as positive
evidence that the band is on while HR Data Broadcast is off, and the dashboard
shows that instruction instead of a generic connection error.

### 4.2 Normal-endpoint name mismatch

The live normal endpoint advertises as **`HUAWEI Band 10-TEST`**, not the
`HUAWEI Band 9-...` form recorded during the first recon. The original name
matcher accepted only `HUAWEI Band 9-`, so the daemon could not classify the
band as nearby even while its normal endpoint was visible. The matcher now
accepts `HUAWEI Band <model>-...` and explicitly excludes the `HUAWEI Band HR-`
endpoint. With this fix the live daemon reports `band_visible=true` and
`hr_broadcast_active=false` when the band is on but broadcasting is off.

### 4.3 Time zone display

All dashboard timestamps, chart labels, annotation times and retry times are
rendered explicitly in `Asia/Kolkata` (IST, UTC+05:30), independent of the
browser or host time zone. Annotation `datetime-local` values are interpreted
as IST and converted to UTC before storage.


## 5. Reproduce

```bash
# analysis of the real database
band9-analyze --db ~/.local/share/band9/acquisition.sqlite3 --out reports/analysis

# simulation (separate demo database; never the production DB)
BAND9_DATA_DIR="$PWD/data/demo" \
  band9-acquire --simulate --duration 60 --expected-interval 0.5
BAND9_DATA_DIR="$PWD/data/demo" \
  band9-analyze --db "$PWD/data/demo/acquisition.sqlite3" --out reports/demo \
  --include-simulated --expected-interval 0.5
```

## 6. What remains

1. Wake the band and start HR Data Broadcast again (battery was 16%).
2. Confirm the daemon reports `connected`, ~1 s sampling, `band_visible=true`
   and `hr_broadcast_active=true`; the dashboard hint should disappear.
3. Add the first manual sleep annotations.
4. Run the controlled A/B/C experiment in `17_acquisition_system.md` §10.
5. Reboot the host once and verify the daemon resumes automatically (the only
   validation item not yet exercised).
6. After 28 days, generate the baseline report and review the daily/rolling
   trends; continue acquisition afterwards for longitudinal comparison.

## 7. Method caveats

- PC reception time is not sensor acquisition time; HRS provides no timestamp.
- Missing intervals are not zero-filled or interpolated.
- Resting HR is an observed low-activity proxy because activity data is absent.
- Sleep is manual annotation only; no REM/awakening inference.
- The 1 Hz BPM stream is not beat-to-beat HRV; no RMSSD/SDNN/pNN50 is computed.
