"""Read-only loading of the acquisition database for analysis."""

from __future__ import annotations

import json
import sqlite3
from datetime import tzinfo
from pathlib import Path

import pandas as pd


def _connect_readonly(path: str | Path) -> sqlite3.Connection:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"database not found: {target}")
    uri = f"{target.resolve().as_uri()}?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=5.0)


def _read(path: str | Path, sql: str) -> pd.DataFrame:
    with _connect_readonly(path) as conn:
        return pd.read_sql_query(sql, conn)


def _local_tz() -> tzinfo:
    from datetime import datetime

    return datetime.now().astimezone().tzinfo


def load_measurements(
    db_path: str | Path,
    *,
    start: str | None = None,
    end: str | None = None,
    include_simulated: bool = False,
    local_tz: tzinfo | None = None,
) -> pd.DataFrame:
    sql = "SELECT * FROM raw_measurements"
    clauses: list[str] = []
    if start:
        clauses.append(f"timestamp_utc >= '{start}'")
    if end:
        clauses.append(f"timestamp_utc < '{end}'")
    if not include_simulated:
        clauses.append("source != 'simulated'")
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY timestamp_utc ASC"
    df = _read(db_path, sql)
    if df.empty:
        return df

    df["timestamp_utc"] = pd.to_datetime(
        df["timestamp_utc"], utc=True, format="ISO8601", errors="coerce"
    )
    df["received_at_utc"] = pd.to_datetime(
        df["received_at_utc"], utc=True, format="ISO8601", errors="coerce"
    )
    df = df.dropna(subset=["timestamp_utc", "heart_rate_bpm"]).copy()
    df["heart_rate_bpm"] = pd.to_numeric(df["heart_rate_bpm"], errors="coerce")
    df = df.dropna(subset=["heart_rate_bpm"])
    df["session_id"] = pd.to_numeric(df["session_id"], errors="coerce").astype("Int64")
    df["quality"] = df["quality_flags"].map(_parse_quality)
    df["sensor_contact"] = df["quality"].map(lambda q: q.get("sensor_contact"))
    df["simulated"] = df["quality"].map(lambda q: bool(q.get("simulated", False)))
    tz = local_tz or _local_tz()
    df["timestamp_local"] = df["timestamp_utc"].dt.tz_convert(tz)
    df["date_local"] = df["timestamp_local"].dt.date
    return df.sort_values("timestamp_utc").reset_index(drop=True)


def _parse_quality(value: object) -> dict:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def load_annotations(db_path: str | Path, *, local_tz: tzinfo | None = None) -> pd.DataFrame:
    df = _read(
        db_path,
        "SELECT * FROM annotations ORDER BY start_time ASC",
    )
    if df.empty:
        return df
    df["start_time"] = pd.to_datetime(
        df["start_time"], utc=True, format="ISO8601", errors="coerce"
    )
    df["end_time"] = pd.to_datetime(
        df["end_time"], utc=True, format="ISO8601", errors="coerce"
    )
    df = df.dropna(subset=["start_time", "end_time"]).copy()
    tz = local_tz or _local_tz()
    df["start_local"] = df["start_time"].dt.tz_convert(tz)
    df["end_local"] = df["end_time"].dt.tz_convert(tz)
    df["duration_hours"] = (df["end_time"] - df["start_time"]).dt.total_seconds() / 3600.0
    return df


def load_sessions(db_path: str | Path) -> pd.DataFrame:
    return _read(
        db_path,
        "SELECT * FROM monitoring_sessions ORDER BY session_id ASC",
    )


def load_events(db_path: str | Path) -> pd.DataFrame:
    df = _read(db_path, "SELECT * FROM device_events ORDER BY event_id ASC")
    if not df.empty:
        df["event_time_utc"] = pd.to_datetime(
            df["event_time_utc"], utc=True, format="ISO8601", errors="coerce"
        )
    return df


def sleep_mask(df: pd.DataFrame, annotations: pd.DataFrame) -> pd.Series:
    """Boolean mask of samples inside any sleep annotation."""

    mask = pd.Series(False, index=df.index)
    if annotations.empty:
        return mask
    for row in annotations.itertuples():
        if getattr(row, "event_type", "sleep") != "sleep":
            continue
        mask |= (df["timestamp_utc"] >= row.start_time) & (df["timestamp_utc"] < row.end_time)
    return mask


__all__ = [
    "load_annotations",
    "load_events",
    "load_measurements",
    "load_sessions",
    "sleep_mask",
]
