"""Read-only descriptive statistics for the acquisition dashboard.

Design rules
------------
* Never interpolate, zero-fill, or modify observations.
* Group by local calendar hour/day in an explicit timezone (default IST).
* Statistics are computed on the observations that actually exist.
* Time coverage is estimated from observation spacing with a 5 s cap, so a
  long acquisition gap is not counted as monitored time.
* The module reads SQLite through a read-only URI. It never writes.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

DEFAULT_TIMEZONE = "Asia/Kolkata"
DEFAULT_TZ = ZoneInfo(DEFAULT_TIMEZONE)
MAX_GAP_SECONDS = 5.0
SUSTAINED_WINDOW = "5min"
SUSTAINED_MIN_SAMPLES = 150  # 50% of a 5-minute 1 Hz window
TRAJECTORY_MAX_POINTS = 5000
RANGE_KINDS = {
    "current_session",
    "session",
    "1h",
    "6h",
    "12h",
    "24h",
    "today",
    "yesterday",
    "7d",
    "28d",
    "custom",
}


# ---------------------------------------------------------------------------
# Read-only loading
# ---------------------------------------------------------------------------


def _connect_readonly(path: str | Path) -> sqlite3.Connection:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"database not found: {target}")
    uri = f"{target.resolve().as_uri()}?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=5.0)


def _read_frame(path: str | Path, sql: str, params: Iterable[Any]) -> pd.DataFrame:
    with _connect_readonly(path) as conn:
        return pd.read_sql_query(sql, conn, params=list(params))


def load_measurement_frame(
    db_path: str | Path,
    *,
    start: str | None = None,
    end: str | None = None,
    session_id: int | None = None,
    include_simulated: bool = False,
    tz: ZoneInfo = DEFAULT_TZ,
) -> pd.DataFrame:
    """Load only the columns needed for descriptive statistics."""
    clauses: list[str] = []
    params: list[Any] = []
    if start:
        clauses.append("timestamp_utc >= ?")
        params.append(start)
    if end:
        clauses.append("timestamp_utc < ?")
        params.append(end)
    if session_id is not None:
        clauses.append("session_id = ?")
        params.append(session_id)
    if not include_simulated:
        clauses.append("source != 'simulated'")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = (
        "SELECT timestamp_utc, epoch_utc, heart_rate_bpm, session_id, source "
        f"FROM raw_measurements{where} ORDER BY timestamp_utc ASC"
    )
    frame = _read_frame(db_path, sql, params)
    if frame.empty:
        frame = pd.DataFrame(
            columns=["timestamp_utc", "heart_rate_bpm", "session_id", "source"]
        )
        frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
        frame["timestamp_local"] = frame["timestamp_utc"]
        frame["date_local"] = pd.Series(dtype="object")
        frame["hour_local"] = frame["timestamp_local"]
        return frame

    frame["timestamp_utc"] = pd.to_datetime(
        frame["timestamp_utc"], utc=True, errors="coerce"
    )
    frame["heart_rate_bpm"] = pd.to_numeric(
        frame["heart_rate_bpm"], errors="coerce"
    )
    frame = frame.dropna(subset=["timestamp_utc", "heart_rate_bpm"]).copy()
    frame["session_id"] = pd.to_numeric(
        frame["session_id"], errors="coerce"
    ).astype("Int64")
    frame["timestamp_local"] = frame["timestamp_utc"].dt.tz_convert(tz)
    frame["date_local"] = frame["timestamp_local"].dt.date
    frame["hour_local"] = frame["timestamp_local"].dt.floor("h")
    return frame.sort_values("timestamp_utc").reset_index(drop=True)


def load_events_frame(
    db_path: str | Path,
    *,
    start: str | None = None,
    end: str | None = None,
    event_types: list[str] | None = None,
    tz: ZoneInfo = DEFAULT_TZ,
) -> pd.DataFrame:
    clauses: list[str] = []
    params: list[Any] = []
    if start:
        clauses.append("event_time_utc >= ?")
        params.append(start)
    if end:
        clauses.append("event_time_utc < ?")
        params.append(end)
    if event_types:
        clauses.append("event_type IN (" + ",".join("?" for _ in event_types) + ")")
        params.extend(event_types)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = (
        "SELECT event_time_utc, event_type, session_id, details "
        f"FROM device_events{where} ORDER BY event_time_utc ASC"
    )
    frame = _read_frame(db_path, sql, params)
    if frame.empty:
        return frame
    frame["event_time_utc"] = pd.to_datetime(
        frame["event_time_utc"], utc=True, errors="coerce"
    )
    frame = frame.dropna(subset=["event_time_utc"]).copy()
    frame["event_time_local"] = frame["event_time_utc"].dt.tz_convert(tz)
    return frame


def load_session_row(
    db_path: str | Path, *, session_id: int | None = None
) -> dict[str, Any] | None:
    sql = (
        "SELECT session_id, start_time, end_time, connection_status, "
        "total_measurements FROM monitoring_sessions"
    )
    params: list[Any] = []
    if session_id is None:
        sql += " ORDER BY session_id DESC LIMIT 1"
    else:
        sql += " WHERE session_id = ? LIMIT 1"
        params.append(session_id)
    frame = _read_frame(db_path, sql, params)
    return None if frame.empty else frame.iloc[0].to_dict()


# ---------------------------------------------------------------------------
# Range resolution
# ---------------------------------------------------------------------------


def _parse_datetime(value: str, *, tz: ZoneInfo) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(UTC)


def _range_label(kind: str) -> str:
    return {
        "current_session": "Current session",
        "1h": "Last 1 hour",
        "6h": "Last 6 hours",
        "12h": "Last 12 hours",
        "24h": "Last 24 hours",
        "today": "Today",
        "yesterday": "Yesterday",
        "7d": "Last 7 days",
        "28d": "Last 28 days",
        "custom": "Custom range",
    }.get(kind, kind)


def resolve_range(
    kind: str,
    *,
    start: str | None = None,
    end: str | None = None,
    now: datetime | None = None,
    tz: ZoneInfo = DEFAULT_TZ,
    session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a dashboard range to UTC bounds.

    ``current_session`` uses the supplied session, falling back to the last
    24 hours when no session exists. ``today`` is elapsed-to-now; ``yesterday``
    is a complete local calendar day. Rolling windows end at ``now``.
    """
    normalized = kind.strip().lower().replace("last ", "").replace("last_", "")
    if normalized in ("current", "current_session", "session"):
        normalized = "current_session"
    if normalized not in RANGE_KINDS:
        raise ValueError(f"unknown range: {kind}")

    now = (now or datetime.now(tz=UTC)).astimezone(UTC)
    label = _range_label(normalized)
    partial = False
    warning: str | None = None

    if normalized == "current_session":
        if session is None:
            normalized = "24h"
            label = "Last 24 hours (no session)"
            warning = "No monitoring session found; showing the last 24 hours."
            start_dt = now - timedelta(hours=24)
            end_dt = now
        else:
            start_dt = _parse_datetime(str(session["start_time"]), tz=tz)
            if session.get("end_time"):
                end_dt = _parse_datetime(str(session["end_time"]), tz=tz)
            else:
                end_dt = now
                partial = True
    elif normalized in ("1h", "6h", "12h", "24h", "7d", "28d"):
        hours = {"1h": 1, "6h": 6, "12h": 12, "24h": 24, "7d": 168, "28d": 672}[
            normalized
        ]
        end_dt = now
        start_dt = now - timedelta(hours=hours)
    elif normalized == "today":
        local_now = now.astimezone(tz)
        start_dt = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(
            UTC
        )
        end_dt = now
        partial = True
    elif normalized == "yesterday":
        local_today = now.astimezone(tz).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        start_dt = (local_today - timedelta(days=1)).astimezone(UTC)
        end_dt = local_today.astimezone(UTC)
    else:  # custom
        if not start or not end:
            raise ValueError("custom range requires start and end")
        start_dt = _parse_datetime(start, tz=tz)
        end_dt = _parse_datetime(end, tz=tz)
        partial = end_dt > now
        warning = "Custom range extends into the future; available data only." if partial else None

    if end_dt <= start_dt:
        raise ValueError("range end must be after start")

    duration = (end_dt - start_dt).total_seconds()
    return {
        "kind": normalized,
        "label": label,
        "start_utc": start_dt.isoformat(timespec="milliseconds"),
        "end_utc": end_dt.isoformat(timespec="milliseconds"),
        "start_local": start_dt.astimezone(tz).isoformat(timespec="seconds"),
        "end_local": end_dt.astimezone(tz).isoformat(timespec="seconds"),
        "duration_seconds": round(duration, 3),
        "timezone": str(tz),
        "partial": partial,
        "warning": warning,
    }


# ---------------------------------------------------------------------------
# Core statistics
# ---------------------------------------------------------------------------


def _clean(values: Iterable[Any]) -> np.ndarray:
    cleaned = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            cleaned.append(number)
    return np.asarray(cleaned, dtype=float)


def summary_stats(values: Iterable[Any]) -> dict[str, Any] | None:
    """Descriptive statistics; SD is sample SD (ddof=1), MAD is unscaled."""
    data = _clean(values)
    if data.size == 0:
        return None
    mean = float(np.mean(data))
    median = float(np.median(data))
    q25, q75 = np.percentile(data, [25, 75])
    p05, p95 = np.percentile(data, [5, 95])
    sd = float(np.std(data, ddof=1)) if data.size > 1 else 0.0
    mad = float(np.median(np.abs(data - median)))
    return {
        "count": int(data.size),
        "mean": round(mean, 3),
        "median": round(median, 3),
        "min": round(float(np.min(data)), 3),
        "max": round(float(np.max(data)), 3),
        "sd": round(sd, 3),
        "mad": round(mad, 3),
        "iqr": round(float(q75 - q25), 3),
        "p05": round(float(p05), 3),
        "p95": round(float(p95), 3),
        "cv": round((sd / mean) * 100.0, 3) if mean else None,
        "range": round(float(np.max(data) - np.min(data)), 3),
    }


def monitored_duration_seconds(timestamps: Iterable[Any]) -> float:
    """Estimate monitored time from sample spacing, capping gaps at 5 s."""
    values = sorted(pd.to_datetime(list(timestamps), utc=True, errors="coerce").dropna())
    if len(values) < 2:
        return 0.0
    index = pd.DatetimeIndex(values)
    seconds = np.diff(index.asi8) / 1e9
    seconds = np.clip(seconds, 0.0, MAX_GAP_SECONDS)
    return float(np.sum(seconds) + np.median(seconds))


def _coverage(duration: float, period_seconds: float) -> float | None:
    if period_seconds <= 0:
        return None
    return round(min(1.0, max(0.0, duration / period_seconds)), 4)


def _time_weighted_mean(timestamps: pd.Series, values: pd.Series) -> float | None:
    if len(values) == 0:
        return None
    if len(values) == 1:
        return round(float(values.iloc[0]), 3)
    seconds = timestamps.astype("int64").to_numpy(dtype=float) / 1e9
    deltas = np.diff(seconds)
    weights = np.clip(deltas, 0.0, MAX_GAP_SECONDS)
    weights = np.append(weights, float(np.median(weights)) if len(weights) else 1.0)
    total = float(np.sum(weights))
    if total <= 0:
        return round(float(np.mean(values)), 3)
    return round(float(np.sum(values.to_numpy(dtype=float) * weights) / total), 3)


def _sustained_extremes(group: pd.DataFrame) -> tuple[float | None, float | None]:
    series = group.set_index("timestamp_utc")["heart_rate_bpm"].sort_index()
    if len(series) < 2:
        return None, None
    rolling = series.rolling(SUSTAINED_WINDOW, min_periods=SUSTAINED_MIN_SAMPLES).mean()
    rolling = rolling.dropna()
    if rolling.empty:
        return None, None
    return round(float(rolling.min()), 3), round(float(rolling.max()), 3)


def sustained_extremes(group: pd.DataFrame) -> tuple[float | None, float | None]:
    """Public alias for the rolling five-minute minimum/maximum."""
    return _sustained_extremes(group)


def _row_stats(group: pd.DataFrame) -> dict[str, Any]:
    stats = summary_stats(group["heart_rate_bpm"]) or {
        "count": 0,
        "mean": None,
        "median": None,
        "min": None,
        "max": None,
        "sd": None,
        "mad": None,
        "iqr": None,
        "p05": None,
        "p95": None,
        "cv": None,
        "range": None,
    }
    duration = monitored_duration_seconds(group["timestamp_utc"])
    return {
        **stats,
        "duration_seconds": round(duration, 3),
        "start_utc": group["timestamp_utc"].min().isoformat(timespec="milliseconds"),
        "end_utc": group["timestamp_utc"].max().isoformat(timespec="milliseconds"),
        "low_coverage": False,
        "small_sample": stats["count"] < 10,
    }


def summary_block(frame: pd.DataFrame, range_info: dict[str, Any]) -> dict[str, Any]:
    if frame.empty:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "min": None,
            "max": None,
            "sd": None,
            "mad": None,
            "iqr": None,
            "p05": None,
            "p95": None,
            "cv": None,
            "range": None,
            "duration_seconds": 0.0,
            "coverage": 0.0,
            "warnings": ["No measurements in this range."],
        }
    stats = summary_stats(frame["heart_rate_bpm"]) or {}
    duration = monitored_duration_seconds(frame["timestamp_utc"])
    coverage = _coverage(duration, float(range_info["duration_seconds"]))
    warnings: list[str] = []
    if range_info.get("warning"):
        warnings.append(str(range_info["warning"]))
    if stats.get("count", 0) < 10:
        warnings.append("Small sample (n < 10); descriptive statistics are unstable.")
    if coverage is not None and coverage < 0.5:
        warnings.append("Coverage below 50%; this range is mostly unmonitored.")
    if range_info.get("partial"):
        warnings.append("Period is still in progress; only available data is shown.")
    return {
        **stats,
        "duration_seconds": round(duration, 3),
        "coverage": coverage,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Aggregation tables
# ---------------------------------------------------------------------------


def _hour_bins(start_local: datetime, end_local: datetime) -> list[pd.Timestamp]:
    cursor = pd.Timestamp(start_local).floor("h")
    stop = pd.Timestamp(end_local)
    bins: list[pd.Timestamp] = []
    while cursor < stop:
        bins.append(cursor)
        cursor = cursor + pd.Timedelta(hours=1)
    return bins


def hourly_table(
    frame: pd.DataFrame,
    range_info: dict[str, Any],
    *,
    tz: ZoneInfo = DEFAULT_TZ,
    include_empty: bool = True,
) -> list[dict[str, Any]]:
    start_local = _parse_datetime(range_info["start_utc"], tz=tz).astimezone(tz)
    end_local = _parse_datetime(range_info["end_utc"], tz=tz).astimezone(tz)
    groups = {
        key: group
        for key, group in frame.groupby("hour_local", sort=True)
    }
    bins = _hour_bins(start_local, end_local) if include_empty else sorted(groups)
    rows: list[dict[str, Any]] = []
    for hour_start in bins:
        hour_start = pd.Timestamp(hour_start).tz_convert(tz)
        hour_end = hour_start + pd.Timedelta(hours=1)
        period_start = max(hour_start, pd.Timestamp(start_local))
        period_end = min(hour_end, pd.Timestamp(end_local))
        period_seconds = max(0.0, (period_end - period_start).total_seconds())
        group = groups.get(hour_start)
        if group is None or group.empty:
            stats = summary_stats([]) or {
                "count": 0,
                "mean": None,
                "median": None,
                "min": None,
                "max": None,
                "sd": None,
                "mad": None,
                "iqr": None,
                "p05": None,
                "p95": None,
                "cv": None,
                "range": None,
            }
            row = {
                **stats,
                "duration_seconds": 0.0,
                "coverage": 0.0,
                "start_utc": None,
                "end_utc": None,
                "small_sample": False,
                "low_coverage": True,
            }
        else:
            row = _row_stats(group)
            row["coverage"] = _coverage(
                float(row["duration_seconds"]), period_seconds
            )
            row["low_coverage"] = bool(
                row["coverage"] is not None and row["coverage"] < 0.5
            )
        rows.append(
            {
                "date": hour_start.date().isoformat(),
                "hour": f"{hour_start:%H:%M}–{hour_end:%H:%M}",
                "label": f"{hour_start:%d %b %Y, %H:%M}–{hour_end:%H:%M}",
                "hour_start_utc": hour_start.tz_convert(UTC).isoformat(
                    timespec="milliseconds"
                ),
                "hour_end_utc": hour_end.tz_convert(UTC).isoformat(
                    timespec="milliseconds"
                ),
                **row,
            }
        )
    return rows


def daily_table(
    frame: pd.DataFrame,
    events: pd.DataFrame,
    range_info: dict[str, Any],
    *,
    tz: ZoneInfo = DEFAULT_TZ,
) -> list[dict[str, Any]]:
    start_local = _parse_datetime(range_info["start_utc"], tz=tz).astimezone(tz)
    end_local = _parse_datetime(range_info["end_utc"], tz=tz).astimezone(tz)
    groups = {key: group for key, group in frame.groupby("date_local", sort=True)}
    disconnect_dates: dict[date, int] = {}
    if not events.empty:
        disconnects = events[events["event_type"] == "disconnected"]
        for day, count in disconnects["event_time_local"].dt.date.value_counts().items():
            disconnect_dates[day] = int(count)

    rows: list[dict[str, Any]] = []
    day = start_local.date()
    last_day = end_local.date()
    while day <= last_day:
        day_start_local = pd.Timestamp(datetime.combine(day, time.min, tzinfo=tz))
        day_end_local = day_start_local + pd.Timedelta(days=1)
        period_start = max(day_start_local, pd.Timestamp(start_local))
        period_end = min(day_end_local, pd.Timestamp(end_local))
        period_seconds = max(0.0, (period_end - period_start).total_seconds())
        group = groups.get(day)
        if group is None or group.empty:
            stats = summary_stats([]) or {
                "count": 0,
                "mean": None,
                "median": None,
                "min": None,
                "max": None,
                "sd": None,
                "mad": None,
                "iqr": None,
                "p05": None,
                "p95": None,
                "cv": None,
                "range": None,
            }
            row = {
                **stats,
                "duration_seconds": 0.0,
                "coverage": 0.0,
                "min_timestamp_utc": None,
                "max_timestamp_utc": None,
                "sustained_5min_min": None,
                "sustained_5min_max": None,
                "time_weighted_mean": None,
                "small_sample": False,
                "low_coverage": True,
            }
        else:
            row = _row_stats(group)
            ordered = group.sort_values("timestamp_utc")
            min_at = ordered.loc[ordered["heart_rate_bpm"].idxmin(), "timestamp_utc"]
            max_at = ordered.loc[ordered["heart_rate_bpm"].idxmax(), "timestamp_utc"]
            sustained_min, sustained_max = _sustained_extremes(ordered)
            row.update(
                {
                    "coverage": _coverage(
                        float(row["duration_seconds"]), period_seconds
                    ),
                    "min_timestamp_utc": min_at.isoformat(timespec="milliseconds"),
                    "max_timestamp_utc": max_at.isoformat(timespec="milliseconds"),
                    "sustained_5min_min": sustained_min,
                    "sustained_5min_max": sustained_max,
                    "time_weighted_mean": _time_weighted_mean(
                        ordered["timestamp_utc"], ordered["heart_rate_bpm"]
                    ),
                    "low_coverage": bool(
                        _coverage(float(row["duration_seconds"]), period_seconds)
                        is not None
                        and _coverage(float(row["duration_seconds"]), period_seconds) < 0.5
                    ),
                }
            )
        rows.append(
            {
                "date": day.isoformat(),
                "disconnected_intervals": int(disconnect_dates.get(day, 0)),
                **row,
            }
        )
        day = day + timedelta(days=1)
    return rows


def trajectory_points(
    frame: pd.DataFrame, *, max_points: int = TRAJECTORY_MAX_POINTS
) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    ordered = frame.sort_values("timestamp_utc")
    step = max(1, math.ceil(len(ordered) / max_points))
    sampled = ordered.iloc[::step]
    if len(ordered) and sampled.index[-1] != ordered.index[-1]:
        sampled = pd.concat([sampled, ordered.iloc[[-1]]])
    return [
        {
            "timestamp_utc": row.timestamp_utc.isoformat(timespec="milliseconds"),
            "heart_rate_bpm": int(row.heart_rate_bpm),
        }
        for row in sampled.itertuples()
    ]


__all__ = [
    "DEFAULT_TIMEZONE",
    "DEFAULT_TZ",
    "daily_table",
    "hourly_table",
    "load_events_frame",
    "load_measurement_frame",
    "load_session_row",
    "monitored_duration_seconds",
    "resolve_range",
    "summary_block",
    "summary_stats",
    "sustained_extremes",
    "trajectory_points",
]
