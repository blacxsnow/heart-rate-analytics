"""Collector and simulation tests that do not touch BLE hardware."""

from __future__ import annotations

import asyncio

from fitness_band.acquisition.collector import BandHRCollector, CollectorConfig
from fitness_band.acquisition.simulation import SimulatedCollector
from fitness_band.acquisition.spool import SpoolQueue
from fitness_band.acquisition.state import StateWriter
from fitness_band.database import AcquisitionDB


def make_collector(tmp_path):
    db = AcquisitionDB(tmp_path / "acq.sqlite3")
    state = StateWriter(tmp_path / "state.json")
    spool = SpoolQueue(tmp_path / "spool")
    collector = BandHRCollector(
        db=db,
        state=state,
        spool=spool,
        control_path=str(tmp_path / "control.json"),
        config=CollectorConfig(scan_timeout=0.1),
    )
    collector._session_id = db.start_session(device_id="test")
    return db, state, collector


def test_handle_packet_persists_and_updates_state(tmp_path) -> None:
    db, state, collector = make_collector(tmp_path)
    collector._handle_packet(bytes([0x06, 85, 0x00]))
    rows = db.recent_measurements(minutes=10_000_000)
    assert len(rows) == 1
    assert rows[0]["heart_rate_bpm"] == 85
    assert state.snapshot()["current_hr"] == 85
    assert "sensor_contact" in rows[0]["quality_flags"]
    db.close()


def test_parse_error_is_event_not_measurement(tmp_path) -> None:
    db, _state, collector = make_collector(tmp_path)
    collector._handle_packet(b"")
    assert db.recent_measurements(minutes=10_000_000) == []
    events = db.events(event_types=["parse_error"])
    assert len(events) == 1
    db.close()


def test_backoff_grows_and_is_capped(tmp_path) -> None:
    _db, _state, collector = make_collector(tmp_path)
    collector._failures = 1
    first = collector._backoff_seconds()
    collector._failures = 5
    later = collector._backoff_seconds()
    assert later >= first
    assert later <= collector.config.backoff_max + 1.0


def test_simulation_end_to_end(tmp_path) -> None:
    db = AcquisitionDB(tmp_path / "acq.sqlite3")
    state = StateWriter(tmp_path / "state.json")
    spool = SpoolQueue(tmp_path / "spool")
    sim = SimulatedCollector(
        db=db,
        state=state,
        spool=spool,
        control_path=str(tmp_path / "control.json"),
        interval=0.2,
    )
    asyncio.run(sim.run(duration=1.0))
    rows = db.recent_measurements(minutes=10_000_000)
    assert len(rows) >= 3
    assert all(row["source"] == "simulated" for row in rows)
    sessions = db.sessions()
    assert sessions and sessions[0]["end_time"] is not None
    events = db.events()
    assert any(event["event_type"] == "monitoring_started" for event in events)
    db.close()


def test_database_failure_spools_instead_of_dropping(tmp_path) -> None:
    db, _state, collector = make_collector(tmp_path)
    db.close()  # force the insert path to fail
    collector._handle_packet(bytes([0x06, 88, 0x00]))
    assert collector.spool.pending_count() == 1
