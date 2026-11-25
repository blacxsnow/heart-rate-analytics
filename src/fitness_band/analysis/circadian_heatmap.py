"""Date × hour-of-day HR heatmap statistics."""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from .descriptive import summary_stats


def heatmap_report(frame: pd.DataFrame, *, tz: ZoneInfo) -> dict[str, Any]:
    if frame.empty:
        return {
            "available": False,
            "dates": [],
            "hours": list(range(24)),
            "cells": [],
            "metrics": ["mean", "median", "sd", "mad", "p95"],
        }
    working = frame.copy()
    working["hour"] = working["timestamp_local"].dt.hour
    cells: list[dict[str, Any]] = []
    for (day, hour), group in working.groupby(
        ["date_local", "hour"], sort=True, dropna=False
    ):
        stats = summary_stats(group["heart_rate_bpm"])
        if stats is None:
            continue
        cells.append(
            {
                "date": day.isoformat() if hasattr(day, "isoformat") else str(day),
                "hour": int(hour),
                "count": stats["count"],
                "mean": stats["mean"],
                "median": stats["median"],
                "sd": stats["sd"],
                "mad": stats["mad"],
                "p95": stats["p95"],
            }
        )
    dates = sorted({cell["date"] for cell in cells})
    return {
        "available": bool(cells),
        "dates": dates,
        "hours": list(range(24)),
        "cells": cells,
        "metrics": ["mean", "median", "sd", "mad", "p95"],
        "note": "Cells use local calendar date and hour; empty cells are not imputed.",
    }


__all__ = ["heatmap_report"]
