"""Rolling baselines and provisional longitudinal deviation analysis.

The rolling series is computed from one-minute means, then downsampled to hourly
points for the browser. This is exploratory and is not a clinical alert system.
"""

from __future__ import annotations

import math
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .descriptive import summary_stats

WINDOWS = {
    "1h": (60, 6),
    "6h": (360, 36),
    "24h": (1440, 144),
    "7d": (10080, 1008),
    "28d": (40320, 4032),
}


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
            "method": "overall median (no 10-minute windows)",
        }
    return {
        "bpm": round(float(np.quantile(series.to_numpy(dtype=float), 0.10)), 3),
        "method": "lower decile of 10-minute medians",
    }


def _sleep_baseline(sleep_history: list[dict[str, Any]]) -> dict[str, Any] | None:
    values = [
        float(row["median"])
        for row in sleep_history
        if row.get("median") is not None
    ]
    if not values:
        return None
    return {
        "bpm": round(float(np.median(values)), 3),
        "nights": len(values),
        "method": "median of annotated-night median HR",
    }


def _value(value: Any, digits: int = 3) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, digits)


def baseline_report(
    frame: pd.DataFrame,
    sleep_history: list[dict[str, Any]],
    *,
    tz: ZoneInfo,
) -> dict[str, Any]:
    if frame.empty:
        return {
            "available": False,
            "baselines": None,
            "series": [],
            "trend": None,
            "warnings": ["No measurements in this range."],
        }

    series = (
        frame.set_index("timestamp_utc")["heart_rate_bpm"]
        .sort_index()
        .resample("1min")
        .mean()
        .dropna()
    )
    rolling = pd.DataFrame(index=series.index)
    for label, (minutes, min_periods) in WINDOWS.items():
        window = f"{minutes}min"
        rolling[f"mean_{label}"] = series.rolling(window, min_periods=min_periods).mean()
        rolling[f"median_{label}"] = (
            series.rolling(window, min_periods=min_periods).median()
        )

    resting = _resting_proxy(frame)
    sleep = _sleep_baseline(sleep_history)
    overall = summary_stats(frame["heart_rate_bpm"])
    assert overall is not None

    if resting:
        rolling["deviation_resting"] = rolling["mean_1h"] - resting["bpm"]
    else:
        rolling["deviation_resting"] = np.nan
    if sleep:
        rolling["deviation_sleep"] = rolling["mean_1h"] - sleep["bpm"]
    else:
        rolling["deviation_sleep"] = np.nan

    mad = float(overall["mad"] or 0.0)
    sd = float(overall["sd"] or 0.0)
    if mad > 0:
        rolling["robust_score"] = (
            rolling["mean_1h"] - float(overall["median"])
        ) / (1.4826 * mad)
    else:
        rolling["robust_score"] = np.nan
    if sd > 0:
        rolling["z_score"] = (rolling["mean_1h"] - float(overall["mean"])) / sd
    else:
        rolling["z_score"] = np.nan

    hourly = rolling.resample("1h").last()
    keys = [
        "mean_1h",
        "median_1h",
        "mean_6h",
        "median_6h",
        "mean_24h",
        "median_24h",
        "mean_7d",
        "median_7d",
        "mean_28d",
        "median_28d",
        "deviation_resting",
        "deviation_sleep",
        "robust_score",
        "z_score",
    ]
    rows = []
    for timestamp, row in hourly.iterrows():
        values = {key: _value(row.get(key)) for key in keys}
        if all(value is None for value in values.values()):
            continue
        rows.append(
            {
                "timestamp_utc": timestamp.isoformat(timespec="milliseconds"),
                **values,
            }
        )

    daily = frame.groupby("date_local")["heart_rate_bpm"].mean().dropna()
    days = len(daily)
    trend = None
    if days >= 2:
        x = np.arange(days, dtype=float)
        y = daily.to_numpy(dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        predicted = slope * x + intercept
        ss_res = float(np.sum((y - predicted) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else None
        trend = {
            "slope_bpm_per_day": round(float(slope), 3),
            "r2": round(float(r2), 3) if r2 is not None else None,
            "days": days,
            "method": "ordinary least squares on daily mean HR",
        }

    warnings = []
    if days < 7:
        warnings.append("Fewer than 7 days of data; baseline is provisional.")
    if days < 28:
        warnings.append("Fewer than 28 days; deviations are exploratory.")
    if sleep is None:
        warnings.append("No annotated sleep baseline is available.")
    if not rows:
        warnings.append("Rolling windows are not yet sufficiently populated.")

    return {
        "available": True,
        "baselines": {
            "resting": resting,
            "sleep": sleep,
            "overall": {
                "mean": overall["mean"],
                "median": overall["median"],
                "sd": overall["sd"],
                "mad": overall["mad"],
                "count": overall["count"],
            },
            "days": days,
            "provisional": days < 28,
            "note": (
                "Baselines are personal and provisional until enough data exists. "
                "They are not clinical thresholds."
            ),
        },
        "series": rows,
        "trend": trend,
        "warnings": warnings,
    }


__all__ = ["baseline_report"]
