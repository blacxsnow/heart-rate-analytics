"""Daily, rolling and 28-day longitudinal HR summaries."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .baseline import observed_resting


def _daily_frame(df: pd.DataFrame, annotations: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    rows = []
    for date, group in df.groupby("date_local", sort=True):
        rows.append(
            {
                "date": pd.Timestamp(date),
                "count": len(group),
                "mean": float(group["heart_rate_bpm"].mean()),
                "median": float(group["heart_rate_bpm"].median()),
                "min": int(group["heart_rate_bpm"].min()),
                "max": int(group["heart_rate_bpm"].max()),
                "observed_resting": (observed_resting(group) or {}).get("bpm"),
            }
        )
    daily = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    if annotations is not None and not annotations.empty and "event_type" in annotations:
        sleep_rows = []
        for row in daily.itertuples():
            day = row.date.date()
            total = 0
            values = []
            for ann in annotations[annotations["event_type"] == "sleep"].itertuples():
                if ann.start_local.date() <= day <= ann.end_local.date():
                    subset = df[
                        (df["timestamp_utc"] >= ann.start_time)
                        & (df["timestamp_utc"] < ann.end_time)
                    ]
                    if not subset.empty:
                        values.append(subset["heart_rate_bpm"])
                        total += len(subset)
            sleep_rows.append(
                {
                    "date": row.date,
                    "sleep_measurements": total,
                    "sleep_median": (float(pd.concat(values).median()) if values else None),
                }
            )
        daily = daily.merge(pd.DataFrame(sleep_rows), on="date", how="left")
    return daily


def longitudinal_report(df: pd.DataFrame, annotations: pd.DataFrame) -> dict[str, Any]:
    daily = _daily_frame(df, annotations)
    if daily.empty:
        return {"available": False, "note": "no measurements"}

    daily["rolling_7d_median"] = daily["median"].rolling(7, min_periods=3).median()
    daily["rolling_28d_mean"] = daily["median"].rolling(28, min_periods=7).mean()
    daily["rolling_28d_sd"] = daily["median"].rolling(28, min_periods=7).std(ddof=1)
    baseline_mean = daily["median"].rolling(28, min_periods=7).mean().shift(1)
    baseline_sd = daily["median"].rolling(28, min_periods=7).std(ddof=1).shift(1)
    daily["baseline_deviation_z"] = (daily["median"] - baseline_mean) / baseline_sd.replace(
        0, np.nan
    )
    daily["ewma_7d"] = daily["median"].ewm(halflife=7, adjust=False).mean()

    first28 = daily.head(28)
    baseline = {
        "days": len(first28),
        "mean_daily_median_bpm": round(float(first28["median"].mean()), 3),
        "sd_daily_median_bpm": round(float(first28["median"].std(ddof=1)), 3)
        if len(first28) > 1
        else 0.0,
        "mean_daily_observed_resting_bpm": round(
            float(first28["observed_resting"].dropna().mean()), 3
        )
        if first28["observed_resting"].notna().any()
        else None,
    }
    variability = (
        round(float(daily["median"].diff().dropna().std(ddof=1)), 3) if len(daily) > 2 else None
    )

    def _clean(value: Any) -> Any:
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
        if isinstance(value, (np.integer, np.floating)):
            return value.item()
        return value

    rows = [
        {key: _clean(value) for key, value in row.items()}
        for row in daily.to_dict(orient="records")
    ]
    return {
        "available": True,
        "days": len(daily),
        "first_28_day_baseline": baseline,
        "day_to_day_variability_bpm": variability,
        "daily": rows,
        "notes": [
            "28-day baseline is a personal empirical reference, not a clinical interval.",
            "Rolling baseline excludes the current day for deviation scores.",
        ],
    }
