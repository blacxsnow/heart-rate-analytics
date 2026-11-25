"""Hourly summaries and exploratory cosinor analysis."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def hourly_stats(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []
    frame = df.copy()
    frame["hour"] = frame["timestamp_local"].dt.hour
    rows = []
    for hour, group in frame.groupby("hour", sort=True):
        values = group["heart_rate_bpm"]
        rows.append(
            {
                "hour": int(hour),
                "count": len(group),
                "mean": round(float(values.mean()), 3),
                "median": round(float(values.median()), 3),
                "sd": round(float(values.std(ddof=1)), 3) if len(values) > 1 else 0.0,
                "p05": round(float(values.quantile(0.05)), 3),
                "p95": round(float(values.quantile(0.95)), 3),
            }
        )
    return rows


def cosinor(hourly: list[dict[str, Any]], *, min_hours: int = 8) -> dict[str, Any] | None:
    usable = [row for row in hourly if row["count"] > 0]
    if len(usable) < min_hours:
        return None
    hours = np.array([row["hour"] for row in usable], dtype=float)
    values = np.array([row["median"] for row in usable], dtype=float)
    omega = 2.0 * np.pi / 24.0
    design = np.column_stack([np.ones_like(hours), np.cos(omega * hours), np.sin(omega * hours)])
    beta, *_ = np.linalg.lstsq(design, values, rcond=None)
    fitted = design @ beta
    residual = values - fitted
    total = np.sum((values - values.mean()) ** 2)
    r2 = 1.0 - (np.sum(residual**2) / total) if total > 0 else 0.0
    mesor, cos_coeff, sin_coeff = (float(x) for x in beta)
    amplitude = float(np.hypot(cos_coeff, sin_coeff))
    acrophase = float(np.arctan2(sin_coeff, cos_coeff) / omega)
    acrophase = acrophase % 24.0
    return {
        "available": True,
        "hours_used": len(usable),
        "mesor_bpm": round(mesor, 3),
        "amplitude_bpm": round(amplitude, 3),
        "acrophase_hour": round(acrophase, 3),
        "r_squared": round(float(r2), 4),
        "model": "y = mesor + amplitude * cos(2*pi*(hour-acrophase)/24)",
        "note": "exploratory 24-h cosine fit; not a clinical circadian marker",
    }
