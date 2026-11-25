# 21 — Statistical Analytics Module

**Status:** P0 implemented (summary cards, hourly table, daily table, hourly
drill-down). P1/P2 are specified but not yet implemented.
**Scope:** read-only extension of the existing acquisition dashboard.
**Non-goals:** no BLE changes, no acquisition-schema changes, no raw-record
updates, no dashboard replacement.

---

## 1. Architecture

```
raw_measurements (append-only)
        │  read-only SQLite URI
        ▼
fitness_band.analysis.descriptive
        │  pandas / numpy
        ▼
GET /api/analytics            GET /api/analytics/trajectory
        │
        ▼
New "Statistical analytics" section below the existing panels
```

- The acquisition daemon, BLE collector, control file, spool, session logic,
  live graph, and existing controls are untouched.
- The analytics module opens SQLite with `mode=ro`; it cannot modify
  observations.
- Simulated rows are excluded by default (`include_simulated=false`).
- The dashboard recalculates every 30 s and on range change.

## 2. Time ranges and timezone

All calendar grouping uses **Asia/Kolkata (IST, UTC+05:30)** by default.
`GET /api/analytics` also accepts `tz=...` for other zones.

| UI range | Meaning |
|---|---|
| Current session | Latest monitoring session start → now (or session end if closed) |
| Last 1 / 6 / 12 / 24 hours | Rolling window ending now |
| Today | Local midnight → now (partial) |
| Yesterday | Previous complete local calendar day |
| Last 7 / 28 days | Rolling window ending now |
| Custom | Explicit local/ISO start and end; future end is marked partial |

Incomplete periods show available data and a warning. They are never filled
with zeros or interpolated.

Hourly rows are **date + hour**, not an aggregate of the same clock hour across
days. For example: `26 Nov 2026, 00:00–01:00`, then `26 Nov 2026, 01:00–02:00`.
Daily rows are one local calendar date each.

## 3. Metric definitions

For observations `x₁ … xₙ` in the selected range:

| Metric | Definition |
|---|---|
| Count | Number of valid BPM observations |
| Mean | Arithmetic mean |
| Median | 50th percentile |
| Minimum / maximum | Lowest / highest observation |
| SD | Sample standard deviation (`ddof=1`; 0 for n=1) |
| MAD | Median of `|xᵢ − median|` (unscaled; not 1.4826×) |
| IQR | P75 − P25 |
| P05 / P95 | 5th / 95th percentile (linear interpolation) |
| CV | `SD / mean × 100` (percent); null when mean is 0 |
| Range | Maximum − minimum |
| Recording duration | Sum of `min(Δᵢ, 5 s)` over adjacent observations, plus the median interval for the last sample |
| Coverage | Recording duration ÷ period duration, clipped to 0–1 |
| Disconnects | Number of `disconnected` events whose local timestamp falls on that day |

### Sustained five-minute HR

A rolling five-minute **mean** over the day's observations, requiring at least
**150 observations** in the window (50% of a 1 Hz five-minute window). The
reported values are the minimum and maximum such rolling means. If no window
has enough observations, the values are null.

### Time-weighted mean

Each observation is weighted by the time until the next observation, capped at
5 s; the last sample receives the median interval as its weight. Gaps longer
than 5 s are therefore not treated as monitored time. This is an estimate, not
an interpolated signal.

### Coverage and missing data

`coverage = monitored seconds / period seconds`. A 24-hour range with 68
minutes of samples has ~4.7% coverage; that is reported explicitly. The
dashboard does not infer values for unmonitored time.

## 4. API

### `GET /api/analytics`

Query parameters:

| Parameter | Default | Meaning |
|---|---|---|
| `range` | `current_session` | `current_session`, `1h`, `6h`, `12h`, `24h`, `today`, `yesterday`, `7d`, `28d`, `custom` |
| `start`, `end` | — | Required for `custom` |
| `session_id` | latest | Optional session filter |
| `include_empty` | auto | Include empty hourly rows; defaults true for ranges ≤ 48 h |
| `include_simulated` | `false` | Include demo rows |
| `tz` | `Asia/Kolkata` | Grouping timezone |

Returns:

```json
{
  "range": {"kind": "24h", "label": "Last 24 hours", "start_utc": "...",
            "end_utc": "...", "start_local": "...", "end_local": "...",
            "duration_seconds": 86400, "timezone": "Asia/Kolkata",
            "partial": false, "session_id": 22},
  "summary": {"count": 3987, "mean": 82.927, "median": 83.0, "min": 63.0,
              "max": 108.0, "sd": 6.047, "mad": 3.0, "iqr": 6.0,
              "p05": 73.0, "p95": 94.0, "cv": 7.292, "range": 45.0,
              "duration_seconds": 4079.5, "coverage": 0.0472,
              "warnings": ["Coverage below 50%; this range is mostly unmonitored."]},
  "hourly": [{"date": "2026-11-26", "hour": "01:00–02:00", ...}],
  "daily": [{"date": "2026-11-26", "sustained_5min_min": 77.8, ...}],
  "warnings": ["..."],
  "computed_at": "..."
}
```

### `GET /api/analytics/trajectory?start=...&end=...`

Returns the raw HR points for a table drill-down (at most 5,000 points, evenly
sampled if longer), plus the same summary block. The current session filter is
passed through so the drill-down matches the table.

## 5. UI behavior

The new **Statistical analytics** section is below the existing dashboard
panels. It adds:

- Range selector (current session, 1/6/12/24 h, today, yesterday, 7/28 days,
  custom).
- Summary cards: samples, mean, median, min, max, SD, MAD, IQR, P05/P95, CV,
  range, coverage.
- Hourly table: date, hour, count, mean, median, min, max, SD, MAD, IQR, P95,
  range, duration, coverage; every column sortable.
- Daily table: date, count, mean, median, min, max, SD, MAD, IQR, P95,
  coverage, duration, min-at, max-at, sustained 5-minute min/max, time-weighted
  mean, disconnects; sortable.
- Clicking an hourly row opens its raw HR trajectory, with gaps preserved.

Existing dashboard elements and controls are not modified. The analytics styles
are scoped under `.analytics`.

## 6. Warnings and limitations

- Fewer than 10 observations: “Small sample; descriptive statistics are
  unstable.”
- Coverage below 50%: “This range is mostly unmonitored.”
- Open current session/today/custom future end: “Period is still in progress.”
- No data: explicit “No measurements in this range.”
- The 1 Hz BPM stream is **not** beat-to-beat HRV. No RMSSD, SDNN or pNN50 is
  computed here.
- Sustained five-minute values are rolling means, not clinical thresholds.
- HR bands, sleep statistics, distribution plots, heatmap and longitudinal
  baselines are the next increments; they will be added without changing the
  acquisition architecture.

## 7. Tests

`tests/test_descriptive.py` covers known summary values, range resolution,
IST hour/date grouping, empty hours, sustained five-minute extremes,
time-weighted means, disconnect counts and warnings.
`tests/test_api.py` covers the analytics endpoint, custom ranges, trajectories,
invalid ranges and the empty-data response.
