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
| Unit/integration suite | **72 passed** |
| Simulated 60 s acquisition | 72 measurements at ~0.5 s; DB/session/events/state written |
| Live dashboard API | status, HR points, CSV export, annotations all returned successfully |
| Sleep annotation | created, listed and deleted; end-before-start normalised to next day |
| Control file | start/stop/reconnect actions persisted atomically |
| Process crash | `SIGKILL` → systemd restarted in ~5 s; old session marked `interrupted`; new session started |
| Web independence | dashboard stayed active across the acquisition restart |
| Empty real DB analysis | `band9-analyze` completed and produced a “no data” report |
| Real reboot | **not performed** — requires a host reboot at a convenient time |
| Real BLE acquisition | **17 samples at ~0.99 s**, then the band stopped advertising; service retry path verified |

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
2. Confirm the daemon reports `connected`, ~1 s sampling and no contact-loss
   flags; the dashboard hint should disappear.
3. Add the first manual sleep annotations.
4. Run the controlled A/B/C experiment in `17_acquisition_system.md` §9.
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
