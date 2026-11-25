"""Sleep-interval HR analysis using manual annotations only."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .baseline import observed_resting, robust_stats
from .data_loader import sleep_mask


def sleep_report(
    df: pd.DataFrame,
    annotations: pd.DataFrame,
    *,
    awake_resting_bpm: float | None = None,
) -> dict[str, Any]:
    if df.empty:
        return {"available": False, "reason": "no measurements"}
    if annotations.empty:
        return {"available": False, "reason": "no manual sleep annotations"}

    sleep_annotations = annotations[annotations["event_type"] == "sleep"]
    if sleep_annotations.empty:
        return {"available": False, "reason": "no sleep annotations"}

    mask = sleep_mask(df, sleep_annotations)
    sleep_df = df[mask]
    if sleep_df.empty:
        return {"available": False, "reason": "no measurements inside sleep intervals"}

    if awake_resting_bpm is None:
        resting = observed_resting(df[~mask])
        awake_resting_bpm = resting["bpm"] if resting else None

    overall = robust_stats(sleep_df["heart_rate_bpm"])
    intervals: list[dict[str, Any]] = []
    for row in sleep_annotations.itertuples():
        subset = sleep_df[
            (sleep_df["timestamp_utc"] >= row.start_time)
            & (sleep_df["timestamp_utc"] < row.end_time)
        ]
        if subset.empty:
            continue
        nadir = subset.loc[subset["heart_rate_bpm"].idxmin()]
        duration_min = (row.end_time - row.start_time).total_seconds() / 60.0
        rolling = (
            subset.set_index("timestamp_utc")["heart_rate_bpm"].resample("5min").median().dropna()
        )
        intervals.append(
            {
                "annotation_id": int(row.annotation_id),
                "start": row.start_time.isoformat(),
                "end": row.end_time.isoformat(),
                "duration_hours": round(duration_min / 60.0, 3),
                "measurements": len(subset),
                "mean": round(float(subset["heart_rate_bpm"].mean()), 3),
                "median": round(float(subset["heart_rate_bpm"].median()), 3),
                "min": int(subset["heart_rate_bpm"].min()),
                "max": int(subset["heart_rate_bpm"].max()),
                "minimum_sustained_bpm": int(rolling.min()) if not rolling.empty else None,
                "nadir_bpm": int(nadir["heart_rate_bpm"]),
                "time_to_nadir_min": round(
                    (nadir["timestamp_utc"] - row.start_time).total_seconds() / 60.0, 3
                ),
            }
        )

    trajectory = _trajectory(sleep_df, sleep_annotations)
    decline = None
    if awake_resting_bpm is not None and overall is not None:
        decline = round(float(awake_resting_bpm) - overall["median"], 3)

    return {
        "available": True,
        "annotations": len(sleep_annotations),
        "nights_with_data": len(intervals),
        "overall": overall,
        "minimum_sustained_bpm": min(
            (
                i["minimum_sustained_bpm"]
                for i in intervals
                if i["minimum_sustained_bpm"] is not None
            ),
            default=None,
        ),
        "awake_resting_bpm": awake_resting_bpm,
        "decline_from_awake_resting_bpm": decline,
        "intervals": intervals,
        "trajectory": trajectory,
        "notes": [
            "Sleep intervals are manual annotations, not inferred from HR.",
            "No REM/awakening classification is performed.",
        ],
    }


def _trajectory(sleep_df: pd.DataFrame, annotations: pd.DataFrame) -> list[dict[str, Any]]:
    frames = []
    for row in annotations.itertuples():
        subset = sleep_df[
            (sleep_df["timestamp_utc"] >= row.start_time)
            & (sleep_df["timestamp_utc"] < row.end_time)
        ].copy()
        if subset.empty:
            continue
        subset["relative_min"] = (
            ((subset["timestamp_utc"] - row.start_time).dt.total_seconds() / 60.0)
            .round()
            .astype(int)
        )
        frames.append(subset[["relative_min", "heart_rate_bpm"]])
    if not frames:
        return []
    combined = pd.concat(frames, ignore_index=True)
    grouped = combined.groupby("relative_min")["heart_rate_bpm"].median().sort_index()
    return [
        {"minute": int(minute), "median_bpm": round(float(value), 3)}
        for minute, value in grouped.items()
        if 0 <= minute <= 24 * 60
    ]
