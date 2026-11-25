"""Tests for the long-running acquisition database."""

from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta

from fitness_band.database import AcquisitionDB, iso_utc, parse_iso


def _measurement(session_id: int, *, ts: float, bpm: int = 70) -> dict:
    iso = iso_utc(ts)
    return {
        "heart_rate_bpm": bpm,
        "device_id": "test-device",
        "session_id": session_id,
        "timestamp_utc": iso,
        "received_at_utc": iso,
        "monotonic_timestamp": ts,
        "epoch_utc": ts,
        "quality_flags": {"sensor_contact": True, "flags": 6},
        "tz_offset_minutes": 0,
    }


def test_session_and_measurements(tmp_path) -> None:
    db = AcquisitionDB(tmp_path / "acq.sqlite3")
    session = db.start_session(device_id="test-device", expected_sampling_interval=1.0)
    db.add_measurement(**_measurement(session, ts=1_700_000_000, bpm=70))
    db.add_measurement(**_measurement(session, ts=1_700_000_001, bpm=70))
    db.add_measurement(**_measurement(session, ts=1_700_000_002, bpm=72))

    stats = db.stats()
    assert stats["total_measurements"] == 3
    sessions = db.sessions()
    assert sessions[0]["session_id"] == session
    assert sessions[0]["total_measurements"] == 3

    points = db.recent_measurements(minutes=10_000_000, limit=10)
    assert [p["heart_rate_bpm"] for p in points] == [70, 70, 72]

    db.end_session(session, status="stopped", actual_sampling_interval=1.0)
    assert db.sessions()[0]["end_time"] is not None
    db.close()


def test_recover_open_sessions(tmp_path) -> None:
    db = AcquisitionDB(tmp_path / "acq.sqlite3")
    session = db.start_session(device_id="d")
    recovered = db.recover_open_sessions()
    assert recovered == [session]
    assert db.sessions()[0]["connection_status"] == "interrupted"
    events = db.events(event_types=["session_interrupted"])
    assert len(events) == 1
    db.close()


def test_annotations_cross_midnight_and_crud(tmp_path) -> None:
    db = AcquisitionDB(tmp_path / "acq.sqlite3")
    start = datetime(2026, 11, 25, 23, 0, tzinfo=UTC)
    end = datetime(2026, 11, 26, 7, 0, tzinfo=UTC)
    # End on the same calendar date must be interpreted as next day.
    annotation = db.add_annotation(
        event_type="sleep",
        start_time=start.isoformat(),
        end_time=datetime(2026, 11, 25, 7, 0, tzinfo=UTC).isoformat(),
        confidence=0.8,
        notes="test",
    )
    row = db.annotations()[0]
    assert parse_iso(row["end_time"]) == end
    assert row["annotation_id"] == annotation

    assert db.update_annotation(annotation, notes="corrected")
    assert db.annotations()[0]["notes"] == "corrected"
    assert db.delete_annotation(annotation)
    assert db.annotations() == []
    db.close()


def test_export_csv(tmp_path) -> None:
    db = AcquisitionDB(tmp_path / "acq.sqlite3")
    session = db.start_session(device_id="d")
    db.add_measurement(**_measurement(session, ts=1_700_000_000))
    target = tmp_path / "out.csv"
    assert db.export_csv(target) == 1
    with target.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["heart_rate_bpm"] == "70"
    db.close()


def test_measurement_interval_validation(tmp_path) -> None:
    db = AcquisitionDB(tmp_path / "acq.sqlite3")
    start = datetime(2026, 11, 25, 23, 0, tzinfo=UTC)
    try:
        db.add_annotation(
            event_type="sleep",
            start_time=start.isoformat(),
            end_time=(start + timedelta(days=3)).isoformat(),
        )
    except ValueError as exc:
        assert "48 hours" in str(exc)
    else:
        raise AssertionError("expected interval rejection")
    db.close()
