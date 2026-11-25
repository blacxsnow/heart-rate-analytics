"""Sleep statistics derived from manual sleep annotations.

The annotation is the source of truth for the sleep interval. HR samples inside
that interval are summarised without interpolation; nights with no samples are
kept as rows with null metrics.
"""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .data_loader import sleep_mask
from .descriptive import summary_stats, sustained_extremes


def _resting_proxy(frame: pd.DataFrame) -> dict[str, Any] | None:
    if frame.empty:
        return None
    series = (
        frame.set_index("timestamp_utc")["heart_rate_bpm"]
        .sort_index()
        .resample("10min")
        .median()
        .dropna()
    )
    if series.empty:
        return {
            "bpm": round(float(frame["heart_rate_bpm"].median()), 3),
            "method": "awake median (no 10-minute windows)",
        }
    return {
        "bpm": round(float(np.quantile(series.to_numpy(dtype=float), 0.10)), 3),
        "method": "lower decile of awake 10-minute medians",
    }


def _aligned_points(
    subset: pd.DataFrame,
    *,
    start: pd.Timestamp,
    tz: ZoneInfo,
) -> list[dict[str, Any]]:
    if subset.empty:
        return []
    series = (
        subset.set_index("timestamp_utc")["heart_rate_bpm"]
        .sort_index()
        .resample("5min")
        .median()
        .dropna()
    )
    points = []
    for timestamp, value in series.items():
        minute = (timestamp - start).total_seconds() / 60.0
        points.append(
            {
                "minute": round(minute),
                "hr": round(float(value), 3),
                "clock": timestamp.tz_convert(tz).strftime("%H:%M"),
            }
        )
    return points


def sleep_report(
    frame: pd.DataFrame,
    annotations: pd.DataFrame,
    *,
    tz: ZoneInfo,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    if frame.empty:
        return {
            "available": False,
            "reason": "no measurements in this range",
            "history": [],
            "aligned": [],
            "mean_trajectory": [],
        }
    if annotations.empty:
        return {
            "available": False,
            "reason": "no sleep annotations in this range",
            "history": [],
            "aligned": [],
            "mean_trajectory": [],
            "note": "Add a sleep annotation above to calculate sleep statistics.",
        }

    if start and end:
        range_start = pd.Timestamp(start)
        range_end = pd.Timestamp(end)
        annotations = annotations[
            (annotations["end_time"] > range_start)
            & (annotations["start_time"] < range_end)
        ]
        if annotations.empty:
            return {
                "available": False,
                "reason": "no sleep annotations in this range",
                "history": [],
                "aligned": [],
                "mean_trajectory": [],
            }

    sleep_annotations = annotations[annotations["event_type"] == "sleep"].copy()
    if sleep_annotations.empty:
        return {
            "available": False,
            "reason": "no sleep annotations",
            "history": [],
            "aligned": [],
            "mean_trajectory": [],
        }

    mask = sleep_mask(frame, sleep_annotations)
    sleep_frame = frame[mask]
    awake = frame[~mask]
    resting = _resting_proxy(awake)

    history: list[dict[str, Any]] = []
    aligned: list[dict[str, Any]] = []
    for annotation in sleep_annotations.itertuples():
        start = pd.Timestamp(annotation.start_time)
        end = pd.Timestamp(annotation.end_time)
        subset = frame[
            (frame["timestamp_utc"] >= start) & (frame["timestamp_utc"] < end)
        ].sort_values("timestamp_utc")
        stats = summary_stats(subset["heart_rate_bpm"]) if not subset.empty else None
        staying_min, staying_max = (
            sustained_extremes(subset) if not subset.empty else (None, None)
        )
        nadir = None
        nadir_time_min = None
        nadir_clock = None
        if stats is not None:
            nadir_row = subset.loc[subset["heart_rate_bpm"].idxmin()]
            nadir = round(float(nadir_row["heart_rate_bpm"]), 3)
            nadir_time_min = round(
                (nadir_row["timestamp_utc"] - start).total_seconds() / 60.0, 1
            )
            nadir_clock = nadir_row["timestamp_utc"].tz_convert(tz).strftime("%H:%M")

        sleep_id = int(annotation.annotation_id)
        row = {
            "sleep_id": sleep_id,
            "start_utc": start.isoformat(),
            "end_utc": end.isoformat(),
            "start_local": start.tz_convert(tz).isoformat(timespec="seconds"),
            "end_local": end.tz_convert(tz).isoformat(timespec="seconds"),
            "confidence": getattr(annotation, "confidence", None),
            "notes": getattr(annotation, "notes", None),
            "duration_hours": round((end - start).total_seconds() / 3600.0, 3),
            "count": stats["count"] if stats else 0,
            "mean": stats["mean"] if stats else None,
            "median": stats["median"] if stats else None,
            "min": stats["min"] if stats else None,
            "max": stats["max"] if stats else None,
            "sd": stats["sd"] if stats else None,
            "mad": stats["mad"] if stats else None,
            "iqr": stats["iqr"] if stats else None,
            "p05": stats["p05"] if stats else None,
            "p95": stats["p95"] if stats else None,
            "sustained_5min_min": staying_min,
            "sustained_5min_max": staying_max,
            "nadir_bpm": nadir,
            "nadir_time_min": nadir_time_min,
            "nadir_clock": nadir_clock,
            "awake_resting": resting["bpm"] if resting else None,
            "delta_vs_awake": (
                round(float(stats["median"]) - resting["bpm"], 3)
                if stats and resting and stats["median"] is not None
                else None
            ),
        }
        history.append(row)
        points = _aligned_points(subset, start=start, tz=tz)
        aligned.append(
            {
                "sleep_id": sleep_id,
                "date": start.tz_convert(tz).date().isoformat(),
                "points": points,
            }
        )

    mean_trajectory: list[dict[str, Any]] = []
    all_points = [
        point
        for night in aligned
        for point in night["points"]
    ]
    if all_points:
        trajectory = pd.DataFrame(all_points)
        grouped = trajectory.groupby("minute")["hr"].agg(["median", "count"]).reset_index()
        mean_trajectory = [
            {
                "minute": int(row.minute),
                "hr": round(float(row.median), 3),
                "nights": int(row.count),
            }
            for row in grouped.itertuples()
        ]

    overall = summary_stats(sleep_frame["heart_rate_bpm"]) if not sleep_frame.empty else None
    overall_sustained = (
        sustained_extremes(sleep_frame) if not sleep_frame.empty else (None, None)
    )
    history_with_data = [row for row in history if row["count"] > 0]
    warnings = []
    if not history_with_data:
        warnings.append("Sleep annotations exist, but no HR samples fall inside them.")
    if resting is None:
        warnings.append("No awake HR is available for the sleep-versus-awake comparison.")
    if len(history_with_data) < 3:
        warnings.append("Fewer than three annotated nights with data; treat as provisional.")

    return {
        "available": True,
        "nights": len(history),
        "nights_with_data": len(history_with_data),
        "overall": (
            {
                **overall,
                "sustained_5min_min": overall_sustained[0],
                "sustained_5min_max": overall_sustained[1],
            }
            if overall
            else None
        ),
        "awake_resting": resting,
        "history": history,
        "aligned": aligned,
        "mean_trajectory": mean_trajectory,
        "warnings": warnings,
        "definitions": {
            "sleep": "samples inside manual sleep annotations",
            "awake_resting": "lower decile of awake 10-minute medians; not clinical resting HR",
            "nadir": "single lowest observed HR sample inside the annotated interval",
            "sustained_5min": "rolling five-minute mean with at least 150 samples",
        },
    }


__all__ = ["sleep_report"]
