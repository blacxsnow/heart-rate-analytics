"""Tests for the read-only analysis application."""

from __future__ import annotations

import pandas as pd

from fitness_band.analysis.baseline import baseline_report, observed_resting, robust_stats
from fitness_band.analysis.circadian import cosinor, hourly_stats
from fitness_band.analysis.dynamics import dynamics_report
from fitness_band.analysis.longitudinal import longitudinal_report
from fitness_band.analysis.quality_control import quality_report
from fitness_band.analysis.sleep_analysis import sleep_report


def synthetic_frame() -> pd.DataFrame:
    start = pd.Timestamp("2026-11-24T22:00:00Z")
    index = pd.date_range(start, periods=8 * 60, freq="1min", tz="UTC")
    # Drop 10 minutes to create a real gap.
    index = index[
        (index < start + pd.Timedelta(minutes=60)) | (index >= start + pd.Timedelta(minutes=70))
    ]
    values = [62 + int(8 * ((i // 60) % 2)) + (i % 5) for i in range(len(index))]
    frame = pd.DataFrame(
        {
            "timestamp_utc": index,
            "received_at_utc": index,
            "epoch_utc": index.astype("int64") / 1e9,
            "heart_rate_bpm": values,
            "session_id": 1,
            "quality": [{"sensor_contact": True} for _ in index],
            "sensor_contact": True,
            "simulated": False,
            "source": "ble_hrs",
        }
    )
    frame["timestamp_local"] = frame["timestamp_utc"].dt.tz_convert("UTC")
    frame["date_local"] = frame["timestamp_local"].dt.date
    return frame


def annotations() -> pd.DataFrame:
    start = pd.Timestamp("2026-11-24T23:00:00Z")
    end = pd.Timestamp("2026-11-25T05:00:00Z")
    return pd.DataFrame(
        [
            {
                "annotation_id": 1,
                "event_type": "sleep",
                "start_time": start,
                "end_time": end,
                "start_local": start,
                "end_local": end,
                "duration_hours": 6.0,
                "confidence": 0.8,
                "notes": None,
            }
        ]
    )


def test_quality_reports_gap_without_imputation() -> None:
    report = quality_report(synthetic_frame())
    assert report["available"] is True
    assert report["total_measurements"] > 400
    assert report["gap_count"] >= 1
    assert report["longest_gap_s"] >= 500
    assert report["completeness"] is not None


def test_baseline_and_observed_resting() -> None:
    frame = synthetic_frame()
    stats = robust_stats(frame["heart_rate_bpm"])
    assert stats["median"] > 0
    resting = observed_resting(frame)
    assert resting["label"] == "observed_resting_low_activity_proxy"
    report = baseline_report(frame, annotations())
    assert report["available"] is True
    assert report["sleep"] is not None
    assert report["awake"] is not None


def test_sleep_report() -> None:
    report = sleep_report(synthetic_frame(), annotations())
    assert report["available"] is True
    assert report["nights_with_data"] == 1
    assert report["overall"]["count"] > 0
    assert report["trajectory"]
    assert report["intervals"][0]["time_to_nadir_min"] >= 0


def test_hourly_and_cosinor() -> None:
    hourly = hourly_stats(synthetic_frame())
    assert len(hourly) >= 6
    fit = cosinor(hourly, min_hours=4)
    assert fit is not None
    assert 0 <= fit["acrophase_hour"] < 24


def test_dynamics_and_longitudinal() -> None:
    frame = synthetic_frame()
    dyn = dynamics_report(frame, annotations())
    assert dyn["available"] is True
    assert dyn["rate_of_change"] is not None
    long = longitudinal_report(frame, annotations())
    assert long["available"] is True
    assert long["days"] >= 2
    assert long["daily"]
    assert long["first_28_day_baseline"]["days"] == long["days"]


def test_empty_inputs() -> None:
    empty = pd.DataFrame()
    assert quality_report(empty)["available"] is False
    assert sleep_report(empty, empty)["available"] is False
    assert longitudinal_report(empty, empty)["available"] is False
