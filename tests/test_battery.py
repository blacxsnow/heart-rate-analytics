"""Tests for charge-aware battery accounting."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fitness_band.analysis.battery import (
    battery_summary,
    parse_battery_charges,
    parse_battery_readings,
)


def _event(event_id: int, kind: str, when: datetime, **details) -> dict:
    return {
        "event_id": event_id,
        "event_type": kind,
        "event_time_utc": when.astimezone(UTC).isoformat(),
        "details": details,
    }


def test_charge_resets_drain_baseline_and_reports_rate() -> None:
    t0 = datetime(2026, 11, 20, 8, 0, tzinfo=UTC)
    events = [
        _event(1, "battery_reading", t0, percent=100),
        _event(2, "battery_reading", t0 + timedelta(hours=2), percent=90),
        _event(
            3,
            "battery_charge",
            t0 + timedelta(hours=3),
            from_percent=40,
            to_percent=100,
            duration_minutes=60,
        ),
        _event(4, "battery_reading", t0 + timedelta(hours=5), percent=95),
    ]
    readings = parse_battery_readings(
        [event for event in events if event["event_type"] == "battery_reading"]
    )
    charges = parse_battery_charges(
        [event for event in events if event["event_type"] == "battery_charge"]
    )
    summary = battery_summary(
        readings, charges, now=t0 + timedelta(hours=6)
    )

    assert summary["display"] == {
        "kind": "reading",
        "percent": 95,
        "recorded_at": (t0 + timedelta(hours=5)).isoformat(timespec="milliseconds"),
        "note": None,
    }
    assert summary["drain"]["available"] is True
    assert summary["drain"]["basis"] == "since_last_charge"
    assert summary["drain"]["start_percent"] == 100
    assert summary["drain"]["end_percent"] == 95
    assert summary["drain"]["hours"] == 2
    assert summary["drain"]["drain_percent_per_hour"] == 2.5
    assert summary["drain"]["drain_percent_per_day"] == 60.0
    assert summary["latest_charge"]["charge_rate_percent_per_hour"] == 60.0
    assert summary["warnings"] == []


def test_drain_uses_last_24_hours_without_charge_events() -> None:
    now = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    readings = parse_battery_readings(
        [
            _event(1, "battery_reading", now - timedelta(hours=30), percent=100),
            _event(2, "battery_reading", now - timedelta(hours=2), percent=90),
            _event(3, "battery_reading", now - timedelta(hours=1), percent=88),
        ]
    )
    summary = battery_summary(readings, [], now=now)

    assert summary["drain"]["basis"] == "last_24h"
    assert summary["drain"]["drain_percent_per_hour"] == 2.0
    assert any("No charge events" in warning for warning in summary["warnings"])


def test_rising_battery_without_charge_is_flagged() -> None:
    now = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    readings = parse_battery_readings(
        [
            _event(1, "battery_reading", now - timedelta(hours=2), percent=80),
            _event(2, "battery_reading", now - timedelta(hours=1), percent=90),
        ]
    )
    summary = battery_summary(readings, [], now=now)

    assert summary["drain"]["drain_percent_per_hour"] == -10.0
    assert any("Battery rose" in warning for warning in summary["warnings"])


def test_charge_without_duration_has_no_rate() -> None:
    t0 = datetime(2026, 11, 20, 8, 0, tzinfo=UTC)
    charges = parse_battery_charges(
        [
            _event(
                1,
                "battery_charge",
                t0,
                from_percent=20,
                to_percent=100,
                duration_minutes=None,
            )
        ]
    )
    summary = battery_summary([], charges, now=t0)

    assert summary["display"]["kind"] == "charge"
    assert summary["display"]["percent"] == 100
    assert summary["latest_charge"]["charge_rate_percent_per_hour"] is None
    assert any("no duration" in warning for warning in summary["warnings"])
    # No reading after the charge means drain cannot start from the charge.
    assert summary["drain"]["available"] is False
    assert "after the last charge" in summary["drain"]["reason"]


def test_charges_are_returned_newest_first() -> None:
    t0 = datetime(2026, 11, 20, 8, 0, tzinfo=UTC)
    charges = parse_battery_charges(
        [
            _event(1, "battery_charge", t0, to_percent=50),
            _event(2, "battery_charge", t0 + timedelta(hours=1), to_percent=100),
        ]
    )
    summary = battery_summary([], charges, now=t0 + timedelta(hours=2))

    assert [row["to_percent"] for row in summary["charges"]] == [100, 50]
