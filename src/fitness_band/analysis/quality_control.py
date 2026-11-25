"""Data-quality metrics that never impute or zero-fill missing observations."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _span_seconds(a: pd.Timestamp, b: pd.Timestamp) -> float:
    return float((b - a).total_seconds())


def quality_report(
    df: pd.DataFrame,
    *,
    expected_interval_s: float = 1.0,
    gap_factor: float = 5.0,
    min_gap_s: float = 5.0,
) -> dict[str, Any]:
    if df.empty:
        return {
            "available": False,
            "total_measurements": 0,
            "note": "no measurements",
        }

    ordered = df.sort_values("timestamp_utc").reset_index(drop=True)
    epochs = ordered["epoch_utc"].astype(float).to_numpy()
    diffs = np.diff(epochs)
    diffs = diffs[diffs > 0]

    observed_median = float(np.median(diffs)) if len(diffs) else expected_interval_s
    observed_median = observed_median or expected_interval_s
    first = ordered["timestamp_utc"].iloc[0]
    last = ordered["timestamp_utc"].iloc[-1]
    span = _span_seconds(first, last)
    expected = round(span / observed_median) + 1 if observed_median > 0 else None
    total = len(ordered)
    completeness = min(1.0, total / expected) if expected else None

    threshold = max(min_gap_s, gap_factor * observed_median)
    gaps = []
    for index, delta in enumerate(diffs, start=1):
        if delta > threshold:
            start = ordered["timestamp_utc"].iloc[index - 1]
            end = ordered["timestamp_utc"].iloc[index]
            gaps.append(
                {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "duration_s": round(float(delta), 3),
                    "missing_estimate": max(0, round(delta / observed_median) - 1),
                }
            )

    daily = (
        ordered.groupby("date_local", dropna=True)
        .agg(
            measurements=("heart_rate_bpm", "size"),
            first=("timestamp_utc", "min"),
            last=("timestamp_utc", "max"),
        )
        .reset_index()
    )
    daily["monitored_hours"] = ((daily["last"] - daily["first"]).dt.total_seconds() / 3600.0).round(
        3
    )
    daily_rows = [
        {
            "date": str(row.date_local),
            "measurements": int(row.measurements),
            "monitored_hours": float(row.monitored_hours),
        }
        for row in daily.itertuples()
    ]

    duplicate_count = int(
        ordered.duplicated(
            subset=["received_at_utc", "heart_rate_bpm", "session_id"], keep=False
        ).sum()
    )

    intervals = np.sort(diffs)
    return {
        "available": True,
        "total_measurements": total,
        "first_measurement": first.isoformat(),
        "last_measurement": last.isoformat(),
        "elapsed_hours": round(span / 3600.0, 3),
        "observed_sampling_interval_s": round(observed_median, 4),
        "configured_sampling_interval_s": expected_interval_s,
        "expected_measurements": expected,
        "completeness": round(completeness, 4) if completeness is not None else None,
        "interval_p05_s": round(float(np.percentile(intervals, 5)), 4) if len(intervals) else None,
        "interval_p50_s": round(float(np.percentile(intervals, 50)), 4) if len(intervals) else None,
        "interval_p95_s": round(float(np.percentile(intervals, 95)), 4) if len(intervals) else None,
        "interval_max_s": round(float(intervals[-1]), 4) if len(intervals) else None,
        "gap_threshold_s": round(threshold, 3),
        "gaps": gaps,
        "longest_gap_s": None if not gaps else max(g["duration_s"] for g in gaps),
        "gap_count": len(gaps),
        "duplicate_candidate_measurements": duplicate_count,
        "daily": daily_rows,
        "session_ids": sorted(int(v) for v in ordered["session_id"].dropna().unique()),
        "notes": [
            "Missing intervals are reported, never zero-filled or interpolated.",
            "Repeated BPM values are retained; only exact duplicate candidates are counted.",
        ],
    }
