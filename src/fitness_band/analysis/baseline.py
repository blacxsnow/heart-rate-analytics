"""Baseline HR statistics with an explicit observed-resting distinction."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .data_loader import sleep_mask


def robust_stats(series: pd.Series) -> dict[str, Any] | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return None
    values = clean.to_numpy(dtype=float)
    median = float(np.median(values))
    q25, q75 = np.percentile(values, [25, 75])
    mad = float(np.median(np.abs(values - median)))
    return {
        "count": len(values),
        "mean": round(float(np.mean(values)), 3),
        "median": round(median, 3),
        "sd": round(float(np.std(values, ddof=1)), 3) if len(values) > 1 else 0.0,
        "mad": round(mad, 3),
        "iqr": round(float(q75 - q25), 3),
        "p05": round(float(np.percentile(values, 5)), 3),
        "p95": round(float(np.percentile(values, 95)), 3),
        "min": round(float(np.min(values)), 3),
        "max": round(float(np.max(values)), 3),
    }


def observed_resting(
    df: pd.DataFrame,
    *,
    window: str = "10min",
    quantile: float = 0.10,
) -> dict[str, Any] | None:
    """A low-activity proxy, not a confirmed resting measurement.

    Activity data is not available from the HRS stream, so this uses the lower
    decile of 10-minute median HR windows. The result is deliberately named
    ``observed_resting`` and must not be presented as a clinical resting HR.
    """

    if df.empty:
        return None
    series = df.set_index("timestamp_utc")["heart_rate_bpm"].sort_index()
    windows = series.resample(window).median().dropna()
    if windows.empty:
        return None
    value = float(np.quantile(windows.to_numpy(dtype=float), quantile))
    return {
        "bpm": round(value, 3),
        "method": f"{window} median windows; p{int(quantile * 100)}",
        "windows": len(windows),
        "label": "observed_resting_low_activity_proxy",
        "confidence": "proxy; activity data unavailable",
    }


def daily_stats(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []
    rows = []
    for date, group in df.groupby("date_local", sort=True):
        values = group["heart_rate_bpm"]
        rows.append(
            {
                "date": str(date),
                "count": len(group),
                "mean": round(float(values.mean()), 3),
                "median": round(float(values.median()), 3),
                "min": int(values.min()),
                "max": int(values.max()),
                "p05": round(float(values.quantile(0.05)), 3),
                "p95": round(float(values.quantile(0.95)), 3),
            }
        )
    return rows


def baseline_report(df: pd.DataFrame, annotations: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {"available": False, "note": "no measurements"}
    mask = sleep_mask(df, annotations)
    sleep = df[mask]
    awake = df[~mask]
    return {
        "available": True,
        "overall": robust_stats(df["heart_rate_bpm"]),
        "observed_resting": observed_resting(df),
        "awake": robust_stats(awake["heart_rate_bpm"]) if not awake.empty else None,
        "sleep": robust_stats(sleep["heart_rate_bpm"]) if not sleep.empty else None,
        "daily": daily_stats(df),
        "definitions": {
            "awake": "samples outside manual sleep annotations",
            "sleep": "samples inside manual sleep annotations",
            "resting": "observed low-activity proxy; not confirmed resting",
        },
    }
