# 21 — Statistical Analytics Module

**Status:** P0, P1 and P2 implemented (summary, hourly, daily, distribution,
HR bands, sleep statistics, circadian heatmap, rolling baselines).
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
| `bin_width` | `5` | Histogram bin width in bpm (1–50) |
| `bands` | default | Comma-separated bands, e.g. `<50,50-59,60-69,70-79,80+` |
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
  "distribution": {"histogram": {...}, "ecdf": {...}, "box": {...},
                    "percentile_bands": [...]},
  "bands": {"bands": [...], "daily": [...], "monitored_seconds": ...},
  "sleep": {"available": true, "history": [...], "aligned": [...],
             "mean_trajectory": [...]},
  "heatmap": {"dates": [...], "hours": [0, ..., 23], "cells": [...]},
  "baseline": {"baselines": {...}, "series": [...], "trend": {...}},
  "warnings": ["..."],
  "computed_at": "..."
}
```

### `GET /api/analytics/trajectory?start=...&end=...`

Returns the raw HR points for a table drill-down (at most 5,000 points, evenly
sampled if longer), plus the same summary block. The current session filter is
passed through so the drill-down matches the table.

### P1/P2 feature definitions

**HR distribution**

- Histogram: fixed-width bins aligned to multiples of `bin_width`.
- ECDF: empirical CDF; unique BPM values with cumulative proportion.
- Box plot: Q1, median, Q3, 1.5×IQR whiskers, outliers outside the whiskers.
- Percentile bands: hourly P05 / median / P95 from the hourly table.

**HR bands**

- Default bands: `<50, 50–59, …, 110–119, 120+`; editable in the UI.
- Duration uses capped 5 s time weights.
- Percentage = band duration ÷ total monitored duration.
- Episodes are contiguous runs in a band; a gap > 5 s starts a new episode.
- Longest episode is the longest such run.
- The stacked daily chart uses duration per local date.
- Bands are descriptive, never diagnostic or exercise-intensity classifications.

**Sleep statistics**

- Uses only manual sleep annotations that overlap the selected range; no sleep
  staging is inferred from HR.
- Per night: mean, median, min, max, SD, MAD, IQR, P05/P95, sustained
  5-minute min/max, nadir, time to nadir, nadir clock time, awake resting proxy,
  and median-sleep minus awake-resting difference.
- Awake resting is the lower decile of awake 10-minute medians; labelled a proxy.
- Sleep-onset-aligned series are 5-minute medians from bedtime; a mean
  trajectory across nights is returned.
- Nights with annotations but no samples remain as rows with null metrics.

**Circadian heatmap**

- One cell per local calendar date × hour.
- Metrics: mean, median, SD, MAD, P95.
- Empty cells are not imputed; the UI renders them dark/grey.

**Rolling baseline**

- One-minute mean series first; rolling windows are 1 h, 6 h, 24 h, 7 d and
  28 d, each with mean and median.
- Minimum observations: 10% of the window (1 h → 6, 6 h → 36, 24 h → 144,
  7 d → 1008, 28 d → 4032 one-minute points). Sparse windows are null.
- Resting baseline: lower decile of 10-minute medians.
- Sleep baseline: median of annotated-night median HR.
- `deviation_resting` / `deviation_sleep` = 1-hour rolling mean minus baseline.
- `robust_score = (mean_1h − overall median) / (1.4826 × overall MAD)`.
- `z_score = (mean_1h − overall mean) / overall SD`.
- Trend is an OLS slope on daily mean HR (bpm/day), with R².
- The baseline is explicitly **provisional** until 28 days exist and is never
  used to issue clinical alerts.

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
- Distribution: histogram, ECDF, box plot and hourly P05–P95 bands; bin width
  selectable (2/5/10 bpm).
- HR bands: editable interval list, duration/%/episodes/longest table and
  stacked daily bars.
- Sleep: per-night table and sleep-onset-aligned trajectory from existing
  annotations.
- Circadian heatmap: date × hour with mean/median/SD/MAD/P95 selector.
- Rolling baseline: 1 h/6 h/24 h/7 d/28 d mean+median cards, rolling chart,
  resting/sleep baselines, deviations, robust/z scores and provisional trend.

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
- HR bands are user-defined descriptive intervals, not diagnostic or
  exercise-intensity labels.
- Heatmap cells with no samples are left empty; they are not interpolated.
- Rolling baselines are provisional until enough data exists and must not drive
  clinical alerts.
- Sleep statistics depend entirely on the accuracy of the manual annotation.

## 7. Tests

`tests/test_descriptive.py` covers summary values, range resolution, IST
hour/date grouping, empty hours, sustained five-minute extremes, time-weighted
means, disconnect counts and warnings.
`tests/test_advanced_analytics.py` covers histogram/ECDF/box, band parsing and
episodes, sleep statistics, heatmap cells, rolling baselines and empty inputs.
`tests/test_api.py` covers the full analytics endpoint, custom bands, sleep
annotations, heatmap/baseline keys, custom ranges, trajectories, invalid ranges
and the empty-data response.

Current suite: **107 tests**. The dashboard was also loaded in headless Chrome
with Playwright: all P0–P2 sections rendered, range/bin-width/metric/bands
interactions worked, hourly drill-down opened and closed, and no console errors
were reported.
