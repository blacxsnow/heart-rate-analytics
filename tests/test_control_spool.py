"""Tests for timestamps, control file and spool."""

from __future__ import annotations

import json

from fitness_band.acquisition.control import apply_action, read_control, write_control
from fitness_band.acquisition.spool import SpoolQueue
from fitness_band.acquisition.timestamping import now_observation


def test_observation_timestamp_fields() -> None:
    observed = now_observation(epoch=1_700_000_000.0, monotonic=42.5)
    assert observed.epoch == 1_700_000_000.0
    assert observed.utc_iso.startswith("2023-11-14T")
    assert observed.monotonic == 42.5
    assert isinstance(observed.tz_offset_minutes, int)
    flags = observed.as_flags()
    assert flags["measurement_time_known"] is False
    assert flags["time_source"] == "pc_reception"


def test_control_actions(tmp_path) -> None:
    path = tmp_path / "control.json"
    assert read_control(path).paused is False
    state = apply_action(path, "stop")
    assert state.paused is True
    state = apply_action(path, "start")
    assert state.paused is False
    first = state.force_reconnect
    state = apply_action(path, "reconnect")
    assert state.force_reconnect == first + 1
    write_control(path, state)
    assert read_control(path).force_reconnect == first + 1


def test_spool_drain_and_retry(tmp_path) -> None:
    spool = SpoolQueue(tmp_path / "spool")
    spool.enqueue({"heart_rate_bpm": 70, "received_at_utc": "2026-11-25T10:00:00.000+00:00"})
    spool.enqueue({"heart_rate_bpm": 71, "received_at_utc": "2026-11-25T10:00:01.000+00:00"})
    assert spool.pending_count() == 2

    inserted = []

    def fail_second(record):
        if record["heart_rate_bpm"] == 71:
            raise RuntimeError("database unavailable")
        inserted.append(record)

    assert spool.drain(fail_second) == 1
    assert [r["heart_rate_bpm"] for r in inserted] == [70]
    assert spool.pending_count() == 1

    inserted.clear()
    assert spool.drain(inserted.append) == 1
    assert [r["heart_rate_bpm"] for r in inserted] == [71]
    assert spool.pending_count() == 0


def test_spool_file_is_jsonl(tmp_path) -> None:
    spool = SpoolQueue(tmp_path / "spool")
    path = spool.enqueue({"heart_rate_bpm": 70, "received_at_utc": "2026-11-25T10:00:00.000+00:00"})
    payload = json.loads(path.read_text(encoding="utf-8").strip())
    assert payload["heart_rate_bpm"] == 70
