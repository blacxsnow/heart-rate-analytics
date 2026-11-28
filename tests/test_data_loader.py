"""Tests for loading mixed-format ISO-8601 timestamps from SQLite."""

from __future__ import annotations

import sqlite3

from fitness_band.analysis.data_loader import load_annotations
from fitness_band.database import AcquisitionDB


def test_load_annotations_parses_mixed_z_and_offset_times(tmp_path) -> None:
    db_file = tmp_path / "acq.sqlite3"
    with AcquisitionDB(db_file):
        pass

    rows = [
        (
            "sleep",
            "2026-11-25T23:15:00.000Z",
            "2026-11-26T04:45:00.000Z",
        ),
        (
            "sleep",
            "2026-11-26T17:30:00+00:00",
            "2026-11-27T00:55:00+00:00",
        ),
        (
            "sleep",
            "2026-11-27T16:15:00+00:00",
            "2026-11-28T00:20:00+00:00",
        ),
    ]
    with sqlite3.connect(db_file) as conn:
        conn.executemany(
            """
            INSERT INTO annotations(
                event_type, start_time, end_time, confidence, notes, created_at, updated_at
            ) VALUES (?, ?, ?, 0.8, NULL, '2026-11-28T00:00:00+00:00',
                      '2026-11-28T00:00:00+00:00')
            """,
            rows,
        )

    frame = load_annotations(db_file)

    assert len(frame) == 3
    assert frame["start_time"].notna().all()
    assert frame["end_time"].notna().all()
    assert frame["start_time"].dt.tz is not None
