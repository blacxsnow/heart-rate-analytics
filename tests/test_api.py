"""Tests for the FastAPI dashboard/annotation/control API."""

from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from fitness_band.api.main import create_app
from fitness_band.database import AcquisitionDB, iso_utc


def make_app(tmp_path):
    app = create_app(
        db_file=tmp_path / "acq.sqlite3",
        state_file=tmp_path / "state.json",
        control_file=tmp_path / "control.json",
        spool_directory=tmp_path / "spool",
        allow_restart=False,
    )
    db: AcquisitionDB = app.state.db
    session = db.start_session(device_id="test", expected_sampling_interval=1.0)
    now = time.time()
    for i in range(5):
        db.add_measurement(
            heart_rate_bpm=70 + i,
            device_id="test",
            session_id=session,
            timestamp_utc=iso_utc(now - 5 + i),
            received_at_utc=iso_utc(now - 5 + i),
            monotonic_timestamp=float(i),
            epoch_utc=now - 5 + i,
            quality_flags={"sensor_contact": True},
        )
    return app


def test_dashboard_and_status(tmp_path) -> None:
    app = make_app(tmp_path)
    with TestClient(app) as client:
        index = client.get("/")
        assert index.status_code == 200
        assert "Band 9" in index.text
        status = client.get("/api/status")
        assert status.status_code == 200
        assert status.json()["database"]["total_measurements"] == 5


def test_hr_points_and_export(tmp_path) -> None:
    app = make_app(tmp_path)
    with TestClient(app) as client:
        hr = client.get("/api/hr?minutes=5")
        assert hr.status_code == 200
        assert len(hr.json()["points"]) == 5
        export = client.get("/api/export.csv")
        assert export.status_code == 200
        assert "heart_rate_bpm" in export.text


def test_annotations_and_control(tmp_path) -> None:
    app = make_app(tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/annotations",
            json={
                "event_type": "sleep",
                "start_time": "2026-11-25T23:00:00+00:00",
                "end_time": "2026-11-25T07:00:00+00:00",
                "confidence": 0.8,
                "notes": "test",
            },
        )
        assert response.status_code == 201
        annotation_id = response.json()["annotation_id"]
        rows = client.get("/api/annotations").json()
        assert rows[0]["annotation_id"] == annotation_id
        assert client.delete(f"/api/annotations/{annotation_id}").status_code == 200

        assert client.post("/api/control", json={"action": "stop"}).status_code == 200
        control = json.loads((tmp_path / "control.json").read_text())
        assert control["paused"] is True
        assert client.post("/api/control", json={"action": "start"}).status_code == 200
        assert client.post("/api/control", json={"action": "restart"}).status_code == 403
