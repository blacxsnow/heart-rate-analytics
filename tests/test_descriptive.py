"""Tests for the read-only descriptive statistics module."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from fitness_band.analysis.descriptive import (
    daily_table,
    hourly_table,
    monitored_duration_seconds,
    resolve_range,
    summary_block,
    summary_stats,
)

TZ = ZoneInfo("Asia/Kolkata")


def make_frame(
    start: str,
    *,
    periods: int,
    freq: str = "1s",
    values: list[int] | None = None,
) -> pd.DataFrame:
    index = pd.date_range(start, periods=periods, freq=freq, tz="UTC")
    if values is None:
        values = [70 + (i % 10) for i in range(len(index))]
    assert len(values) == len(index)
    frame = pd.DataFrame(
        {
            "timestamp_utc": index,
            "epoch_utc": index.as_unit("ns").astype("int64") / 1e9,
            "heart_rate_bpm": values,
            "session_id": 1,
            "source": "ble_hrs",
        }
    )
    frame["timestamp_local"] = frame["timestamp_utc"].dt.tz_convert("Asia/Kolkata")
    frame["date_local"] = frame["timestamp_local"].dt.date
    frame["hour_local"] = frame["timestamp_local"].dt.floor("h")
    return frame


def test_summary_stats_known_values() -> None:
    stats = summary_stats([60, 70, 80, 90])
    assert stats is not None
    assert stats["count"] == 4
    assert stats["mean"] == 75.0
    assert stats["median"] == 75.0
    assert stats["min"] == 60.0
    assert stats["max"] == 90.0
    assert stats["sd"] == 12.91
    assert stats["mad"] == 10.0
    assert stats["iqr"] == 15.0
    assert stats["p05"] == 61.5
    assert stats["p95"] == 88.5
    assert stats["cv"] == 17.213
    assert stats["range"] == 30.0


def test_summary_stats_empty() -> None:
    assert summary_stats([]) is None
    assert summary_stats([None, float("nan"), "bad"]) is None


def test_monitored_duration_caps_gaps() -> None:
    timestamps = pd.to_datetime(
        [
            "2026-11-26T00:00:00Z",
            "2026-11-26T00:00:01Z",
            "2026-11-26T00:00:02Z",
            "2026-11-26T00:00:12Z",
        ],
        utc=True,
    )
    # 1 + 1 + capped 5 + median(1,1,5)=1 => 8
    assert monitored_duration_seconds(timestamps) == 8.0


def test_resolve_ranges_in_ist() -> None:
    now = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
    tz = TZ
    today = resolve_range("today", now=now, tz=tz)
    assert today["start_utc"].startswith("2026-11-25T18:30:00")
    assert today["end_utc"].startswith("2026-11-26T12:00:00")
    assert today["partial"] is True

    yesterday = resolve_range("yesterday", now=now, tz=tz)
    assert yesterday["start_utc"].startswith("2026-11-24T18:30:00")
    assert yesterday["end_utc"].startswith("2026-11-25T18:30:00")
    assert yesterday["partial"] is False

    hour = resolve_range("1h", now=now, tz=tz)
    assert hour["start_utc"].startswith("2026-11-26T11:00:00")

    custom = resolve_range(
        "custom",
        start="2026-11-26T00:00:00+05:30",
        end="2026-11-26T01:00:00+05:30",
        now=now,
        tz=tz,
    )
    assert custom["duration_seconds"] == 3600
    assert custom["start_local"] == "2026-11-26T00:00:00+05:30"

    with pytest.raises(ValueError):
        resolve_range("nonsense", now=now, tz=tz)
    with pytest.raises(ValueError):
        resolve_range("custom", start="2026-11-26T01:00:00Z", end="2026-11-26T00:00:00Z", tz=tz)


def test_hourly_table_groups_by_local_date_and_hour() -> None:
    # 00:00–01:00 IST and 01:00–02:00 IST on 26 Nov.
    frame = make_frame("2026-11-25T18:30:00Z", periods=7200, freq="1s")
    info = resolve_range(
        "custom",
        start="2026-11-25T18:30:00Z",
        end="2026-11-25T20:30:00Z",
        tz=TZ,
    )
    rows = hourly_table(frame, info, include_empty=False)
    assert len(rows) == 2
    assert rows[0]["date"] == "2026-11-26"
    assert rows[0]["hour"].startswith("00:00")
    assert rows[0]["count"] == 3600
    assert rows[1]["hour"].startswith("01:00")
    assert rows[0]["mean"] is not None
    assert rows[0]["coverage"] == 1.0
    assert rows[0]["duration_seconds"] == 3600.0


def test_hourly_table_includes_empty_hours_when_requested() -> None:
    frame = make_frame("2026-11-25T18:30:00Z", periods=60, freq="1s")
    info = resolve_range(
        "custom",
        start="2026-11-25T18:30:00Z",
        end="2026-11-25T21:30:00Z",
        tz=TZ,
    )
    rows = hourly_table(frame, info, include_empty=True)
    assert len(rows) == 3
    assert rows[0]["count"] == 60
    assert rows[1]["count"] == 0
    assert rows[1]["mean"] is None
    assert rows[2]["count"] == 0


def test_daily_table_sustained_and_disconnects() -> None:
    # 10 minutes of 1 Hz data, then a 10-minute gap, then 5 minutes.
    first = make_frame("2026-11-25T18:30:00Z", periods=600, freq="1s")
    second = make_frame("2026-11-25T18:50:00Z", periods=300, freq="1s")
    frame = pd.concat([first, second], ignore_index=True)
    events = pd.DataFrame(
        [
            {
                "event_time_utc": pd.Timestamp("2026-11-25T18:45:00Z"),
                "event_type": "disconnected",
                "event_time_local": pd.Timestamp("2026-11-26T00:15:00+05:30"),
            }
        ]
    )
    info = resolve_range(
        "custom",
        start="2026-11-25T18:30:00Z",
        end="2026-11-25T19:00:00Z",
        tz=TZ,
    )
    rows = daily_table(frame, events, info)
    assert len(rows) == 1
    row = rows[0]
    assert row["date"] == "2026-11-26"
    assert row["count"] == 900
    assert row["disconnected_intervals"] == 1
    assert row["sustained_5min_min"] is not None
    assert row["sustained_5min_max"] is not None
    assert row["time_weighted_mean"] is not None
    assert row["min_timestamp_utc"].startswith("2026-11-25T18:")
    assert row["max_timestamp_utc"].startswith("2026-11-25T18:")
    assert row["coverage"] < 1.0


def test_summary_block_warnings() -> None:
    frame = make_frame("2026-11-25T18:30:00Z", periods=2, freq="1s")
    info = resolve_range(
        "custom",
        start="2026-11-25T18:30:00Z",
        end="2026-11-25T19:30:00Z",
        tz=TZ,
    )
    summary = summary_block(frame, info)
    assert summary["count"] == 2
    assert any("Small sample" in warning for warning in summary["warnings"])
    assert any("Coverage below" in warning for warning in summary["warnings"])
