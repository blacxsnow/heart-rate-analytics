"""Short-term HR dynamics (not beat-to-beat HRV)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .baseline import observed_resting
from .data_loader import sleep_mask


def rate_summary(df: pd.DataFrame) -> dict[str, Any] | None:
    if len(df) < 2:
        return None
    ordered = df.sort_values("timestamp_utc")
    seconds = ordered["timestamp_utc"].diff().dt.total_seconds()
    delta = ordered["heart_rate_bpm"].diff()
    mask = (seconds > 0) & (seconds <= 300) & delta.notna()
    rates = (delta[mask] / (seconds[mask] / 60.0)).abs()
    if rates.empty:
        return None
    return {
        "pairs": len(rates),
        "median_abs_bpm_per_min": round(float(rates.median()), 3),
        "p95_abs_bpm_per_min": round(float(rates.quantile(0.95)), 3),
        "max_abs_bpm_per_min": round(float(rates.max()), 3),
        "note": "variation in reported BPM; not beat-to-beat HRV",
    }


def episodes(
    df: pd.DataFrame, *, threshold_bpm: float, recovery_margin: int = 10
) -> list[dict[str, Any]]:
    if df.empty:
        return []
    ordered = df.sort_values("timestamp_utc").reset_index(drop=True)
    rows: list[dict[str, Any]] = []
    active: list[int] = []
    for index, row in ordered.iterrows():
        if row["heart_rate_bpm"] >= threshold_bpm:
            active.append(index)
        elif active:
            rows.append(_make_episode(ordered, active, threshold_bpm, recovery_margin))
            active = []
    if active:
        rows.append(_make_episode(ordered, active, threshold_bpm, recovery_margin))
    return [row for row in rows if row is not None]


def _make_episode(
    df: pd.DataFrame, indices: list[int], threshold: float, recovery_margin: int
) -> dict[str, Any] | None:
    if len(indices) < 2:
        return None
    start = df.loc[indices[0], "timestamp_utc"]
    end = df.loc[indices[-1], "timestamp_utc"]
    values = df.loc[indices, "heart_rate_bpm"]
    after = df[df["timestamp_utc"] > end]
    recovery = None
    if not after.empty:
        target = threshold - recovery_margin
        recovered = after[after["heart_rate_bpm"] <= target]
        if not recovered.empty:
            recovery = round((recovered.iloc[0]["timestamp_utc"] - end).total_seconds(), 3)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "duration_s": round((end - start).total_seconds(), 3),
        "samples": len(indices),
        "max_bpm": int(values.max()),
        "mean_bpm": round(float(values.mean()), 3),
        "recovery_s": recovery,
    }


def dynamics_report(df: pd.DataFrame, annotations: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {"available": False, "note": "no measurements"}
    mask = sleep_mask(df, annotations)
    awake = df[~mask]
    resting = observed_resting(awake) if not awake.empty else observed_resting(df)
    resting_bpm = resting["bpm"] if resting else None
    values = df["heart_rate_bpm"]
    threshold = max(100.0, float(values.quantile(0.95)) + 5.0)
    events = episodes(df, threshold_bpm=threshold)
    return {
        "available": True,
        "rate_of_change": rate_summary(df),
        "episode_threshold_bpm": round(threshold, 3),
        "episode_count": len(events),
        "episode_total_duration_s": round(sum(e["duration_s"] for e in events), 3),
        "episode_max_bpm": max((e["max_bpm"] for e in events), default=None),
        "episodes": events[:100],
        "observed_resting_bpm": resting_bpm,
        "notes": [
            "Episodes are contiguous samples at/above a descriptive threshold.",
            "No RMSSD/SDNN/pNN50 is calculated from the 1 Hz BPM stream.",
        ],
    }
