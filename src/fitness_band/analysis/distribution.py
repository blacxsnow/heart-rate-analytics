"""HR distribution: histogram, ECDF, box statistics and percentile bands."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

import numpy as np


def _clean(values: Iterable[Any]) -> np.ndarray:
    cleaned: list[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            cleaned.append(number)
    return np.asarray(cleaned, dtype=float)


def histogram(values: Iterable[Any], *, bin_width: float = 5.0) -> dict[str, Any]:
    """Fixed-width histogram; bin edges are aligned to multiples of bin_width."""
    data = _clean(values)
    if data.size == 0:
        return {"available": False, "bin_width": bin_width, "bins": []}
    if bin_width <= 0:
        raise ValueError("bin_width must be positive")
    low = math.floor(float(np.min(data)) / bin_width) * bin_width
    high = math.ceil(float(np.max(data)) / bin_width) * bin_width
    if high <= low:
        high = low + bin_width
    edges = np.arange(low, high + bin_width * 0.5, bin_width)
    counts, edges = np.histogram(data, bins=edges)
    bins = [
        {
            "start": round(float(edges[i]), 3),
            "end": round(float(edges[i + 1]), 3),
            "label": f"{round(edges[i])}–{round(edges[i + 1])}",
            "count": int(counts[i]),
        }
        for i in range(len(counts))
    ]
    return {
        "available": True,
        "bin_width": bin_width,
        "bins": bins,
        "total": int(data.size),
    }


def ecdf(values: Iterable[Any], *, max_points: int = 500) -> dict[str, Any]:
    """Empirical CDF points, downsampled for the browser if necessary."""
    data = np.sort(_clean(values))
    if data.size == 0:
        return {"available": False, "points": []}
    unique, counts = np.unique(data, return_counts=True)
    cumulative = np.cumsum(counts) / data.size
    points = [
        {"bpm": round(float(value), 3), "proportion": round(float(prob), 6)}
        for value, prob in zip(unique, cumulative, strict=True)
    ]
    if len(points) > max_points:
        indexes = np.linspace(0, len(points) - 1, max_points).astype(int)
        points = [points[i] for i in indexes]
    return {"available": True, "points": points, "total": int(data.size)}


def box_stats(values: Iterable[Any]) -> dict[str, Any] | None:
    data = _clean(values)
    if data.size == 0:
        return None
    q1, median, q3 = np.percentile(data, [25, 50, 75])
    iqr = float(q3 - q1)
    low_fence = float(q1) - 1.5 * iqr
    high_fence = float(q3) + 1.5 * iqr
    inside = data[(data >= low_fence) & (data <= high_fence)]
    outliers = data[(data < low_fence) | (data > high_fence)]
    return {
        "min": round(float(np.min(data)), 3),
        "q1": round(float(q1), 3),
        "median": round(float(median), 3),
        "q3": round(float(q3), 3),
        "max": round(float(np.max(data)), 3),
        "whisker_low": round(float(np.min(inside)) if inside.size else float(q1), 3),
        "whisker_high": round(float(np.max(inside)) if inside.size else float(q3), 3),
        "outliers": [round(float(v), 3) for v in outliers[:50]],
        "outlier_count": int(outliers.size),
        "count": int(data.size),
    }


def percentile_bands(hourly_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hourly P05 / median / P95 bands for the percentile-band chart."""
    rows = []
    for row in hourly_rows:
        if row.get("count", 0) == 0:
            continue
        rows.append(
            {
                "timestamp_utc": row["hour_start_utc"],
                "p05": row.get("p05"),
                "median": row.get("median"),
                "p95": row.get("p95"),
            }
        )
    return rows


def distribution_report(
    values: Iterable[Any],
    hourly_rows: list[dict[str, Any]],
    *,
    bin_width: float = 5.0,
) -> dict[str, Any]:
    data = _clean(values)
    if data.size == 0:
        return {
            "available": False,
            "bin_width": bin_width,
            "histogram": {"available": False, "bins": []},
            "ecdf": {"available": False, "points": []},
            "box": None,
            "percentile_bands": [],
            "warnings": ["No measurements in this range."],
        }
    warnings = []
    if data.size < 10:
        warnings.append("Small sample (n < 10); distribution shape is unreliable.")
    return {
        "available": True,
        "bin_width": bin_width,
        "histogram": histogram(data, bin_width=bin_width),
        "ecdf": ecdf(data),
        "box": box_stats(data),
        "percentile_bands": percentile_bands(hourly_rows),
        "warnings": warnings,
    }


__all__ = [
    "box_stats",
    "distribution_report",
    "ecdf",
    "histogram",
    "percentile_bands",
]
