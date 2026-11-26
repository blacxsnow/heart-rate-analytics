"""Tests for P1/P2 analytics: distribution, bands, sleep, heatmap, baselines."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from fitness_band.analysis.baseline_rolling import baseline_report
from fitness_band.analysis.circadian_heatmap import heatmap_report
from fitness_band.analysis.descriptive import resolve_range
from fitness_band.analysis.distribution import (
    box_stats,
    distribution_report,
    ecdf,
    histogram,
)
from fitness_band.analysis.hr_bands import band_report, parse_bands
from fitness_band.analysis.sleep_statistics import sleep_report

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
    frame = pd.DataFrame(
        {
            "timestamp_utc": index,
            "epoch_utc": index.as_unit("ns").astype("int64") / 1e9,
            "heart_rate_bpm": values,
            "session_id": 1,
            "source": "ble_hrs",
        }
    )
    frame["timestamp_local"] = frame["timestamp_utc"].dt.tz_convert(TZ)
    frame["date_local"] = frame["timestamp_local"].dt.date
    frame["hour_local"] = frame["timestamp_local"].dt.floor("h")
    return frame


def test_distribution_components() -> None:
    values = [60, 70, 80, 90]
    hist = histogram(values, bin_width=10)
    assert hist["available"] is True
    assert sum(bin["count"] for bin in hist["bins"]) == 4
    cdf = ecdf(values)
    assert cdf["points"][-1]["proportion"] == 1.0
    box = box_stats(values)
    assert box is not None
    assert box["median"] == 75.0
    assert box["q1"] == 67.5
    assert box["q3"] == 82.5
    report = distribution_report(values, [], bin_width=10)
    assert report["available"] is True
    assert report["histogram"]["total"] == 4
    assert report["percentile_bands"] == []


def test_band_parse_and_report() -> None:
    bands = parse_bands("60-69,70-79,80+")
    assert [band["label"] for band in bands] == ["60–69", "70–79", "80+"]
    with pytest.raises(ValueError):
        parse_bands("70-79,60-69")
    with pytest.raises(ValueError):
        parse_bands("50-70,60-80")

    # 100 samples at 70, 100 at 80, a >5 s gap, then 10 at 60.
    first = make_frame("2026-11-25T18:30:00Z", periods=100, values=[70] * 100)
    second = make_frame("2026-11-25T18:33:20Z", periods=100, values=[80] * 100)
    third = make_frame("2026-11-25T18:37:00Z", periods=10, values=[60] * 10)
    frame = pd.concat([first, second, third], ignore_index=True)
    report = band_report(frame, parse_bands("60-69,70-79,80+"))
    assert report["available"] is True
    by_label = {band["label"]: band for band in report["bands"]}
    assert by_label["70–79"]["episodes"] == 1
    assert by_label["80+"]["episodes"] == 1
    assert by_label["60–69"]["episodes"] == 1
    assert by_label["70–79"]["duration_seconds"] > 0
    assert sum(band["percentage"] for band in report["bands"]) > 99.0
    assert report["daily"]


def test_sleep_statistics() -> None:
    frame = make_frame("2026-11-25T18:30:00Z", periods=3600)
    annotations = pd.DataFrame(
        [
            {
                "annotation_id": 7,
                "event_type": "sleep",
                "start_time": pd.Timestamp("2026-11-25T18:40:00Z"),
                "end_time": pd.Timestamp("2026-11-25T19:10:00Z"),
                "confidence": 0.8,
                "notes": "test",
            }
        ]
    )
    report = sleep_report(frame, annotations, tz=TZ)
    assert report["available"] is True
    assert report["nights"] == 1
    assert report["nights_with_data"] == 1
    night = report["history"][0]
    assert night["count"] == 1800
    assert night["mean"] is not None
    assert night["nadir_clock"] is not None
    assert night["nadir_time_min"] is not None
    assert night["awake_resting"] is not None
    assert night["delta_vs_awake"] is not None
    assert report["aligned"][0]["points"]
    assert report["mean_trajectory"]

    outside = sleep_report(
        frame,
        annotations,
        tz=TZ,
        start="2026-11-25T20:00:00Z",
        end="2026-11-25T21:00:00Z",
    )
    assert outside["available"] is False
    assert "range" in outside["reason"]


def test_heatmap_and_baseline() -> None:
    # Two local hours with data.
    frame = make_frame("2026-11-25T18:30:00Z", periods=7200)
    heatmap = heatmap_report(frame, tz=TZ)
    assert heatmap["available"] is True
    assert heatmap["dates"] == ["2026-11-26"]
    assert len(heatmap["cells"]) == 2
    assert all(cell["mean"] is not None for cell in heatmap["cells"])

    baseline = baseline_report(frame, [], tz=TZ)
    assert baseline["available"] is True
    assert baseline["baselines"]["resting"]["bpm"] > 0
    assert baseline["baselines"]["provisional"] is True
    assert baseline["series"]
    assert baseline["trend"] is None
    assert any("provisional" in warning for warning in baseline["warnings"])


def test_empty_advanced_reports() -> None:
    empty = pd.DataFrame()
    info = resolve_range(
        "1h",
        now=datetime(2026, 11, 26, 12, 0, tzinfo=UTC),
        tz=TZ,
    )
    assert distribution_report([], [], bin_width=5)["available"] is False
    assert band_report(empty, parse_bands(None))["available"] is False
    assert heatmap_report(empty, tz=TZ)["available"] is False
    assert baseline_report(empty, [], tz=TZ)["available"] is False
    assert sleep_report(empty, empty, tz=TZ)["available"] is False
    assert info["kind"] == "1h"
