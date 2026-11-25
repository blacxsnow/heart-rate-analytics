"""Read-only acquisition dashboard and annotation/control API.

The web process never opens the BLE adapter. It reads the acquisition database
and state snapshot, writes sleep annotations, and writes a small control file
that the daemon polls. If this process is stopped, acquisition continues.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from ..acquisition.control import apply_action
from ..acquisition.spool import SpoolQueue
from ..acquisition.state import read_state
from ..analysis.baseline_rolling import baseline_report
from ..analysis.circadian_heatmap import heatmap_report
from ..analysis.data_loader import load_annotations
from ..analysis.descriptive import (
    DEFAULT_TIMEZONE,
    daily_table,
    hourly_table,
    load_events_frame,
    load_measurement_frame,
    load_session_row,
    resolve_range,
    summary_block,
    trajectory_points,
)
from ..analysis.distribution import distribution_report
from ..analysis.hr_bands import band_report, parse_bands
from ..analysis.sleep_statistics import sleep_report
from ..database import AcquisitionDB, iso_utc, parse_iso
from ..paths import control_path as default_control_path
from ..paths import db_path as default_db_path
from ..paths import spool_dir as default_spool_dir
from ..paths import state_path as default_state_path
from .templates import DASHBOARD_HTML


class AnnotationIn(BaseModel):
    event_type: str = "sleep"
    start_time: str
    end_time: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: str | None = None


class AnnotationPatch(BaseModel):
    event_type: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: str | None = None


class ControlIn(BaseModel):
    action: str


class BatteryIn(BaseModel):
    percent: int = Field(ge=0, le=100)
    note: str | None = None


def _epoch(value: str | None) -> float | None:
    if not value:
        return None
    return parse_iso(value).timestamp()


def _disconnect_intervals(db: AcquisitionDB, cutoff: float) -> list[dict[str, Any]]:
    events = db.events(limit=1000, event_types=["connected", "disconnected"])
    events = list(reversed(events))
    intervals: list[dict[str, Any]] = []
    open_start: str | None = None
    for event in events:
        ts = event["event_time_utc"]
        if event["event_type"] == "disconnected":
            open_start = ts
        elif event["event_type"] == "connected" and open_start is not None:
            if (_epoch(ts) or 0) >= cutoff:
                intervals.append({"start": open_start, "end": ts})
            open_start = None
    if open_start is not None:
        intervals.append({"start": open_start, "end": None})
    return intervals


def create_app(
    *,
    db_file: str | Path | None = None,
    state_file: str | Path | None = None,
    control_file: str | Path | None = None,
    spool_directory: str | Path | None = None,
    allow_restart: bool | None = None,
) -> FastAPI:
    db_path = Path(db_file or default_db_path())
    state_path = Path(state_file or default_state_path())
    control_path = Path(control_file or default_control_path())
    spool_path = Path(spool_directory or default_spool_dir())
    restart_allowed = (
        allow_restart
        if allow_restart is not None
        else os.environ.get("BAND9_ALLOW_RESTART", "0") == "1"
    )
    unit = os.environ.get("BAND9_ACQUISITION_UNIT", "huawei-acquisition.service")

    app = FastAPI(title="Huawei Band 9 Acquisition", docs_url=None, redoc_url=None)
    app.state.db = AcquisitionDB(db_path)
    app.state.state_path = state_path
    app.state.control_path = control_path
    app.state.spool = SpoolQueue(spool_path)
    app.state.restart_allowed = restart_allowed
    app.state.unit = unit

    def db() -> AcquisitionDB:
        return app.state.db

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> HTMLResponse:
        return HTMLResponse(DASHBOARD_HTML)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        state = read_state(state_path)
        database = db()
        stats = database.stats()
        sessions = database.sessions(limit=3)
        events = database.events(limit=12)
        pending = app.state.spool.pending_count()
        return {
            "state": state,
            "database": stats,
            "sessions": sessions,
            "events": events,
            "spool_pending": pending,
            "restart_allowed": app.state.restart_allowed,
            "server_time_utc": iso_utc(),
        }

    @app.get("/api/hr")
    def hr(minutes: float = Query(default=5.0, ge=1.0, le=1440.0)) -> dict[str, Any]:
        cutoff = datetime.now(tz=UTC).timestamp() - minutes * 60.0
        rows = db().recent_measurements(minutes=minutes, limit=50000)
        points = []
        for row in rows:
            quality = None
            if row.get("quality_flags"):
                try:
                    quality = json.loads(row["quality_flags"])
                except json.JSONDecodeError:
                    quality = row["quality_flags"]
            points.append(
                {
                    "id": row["id"],
                    "timestamp_utc": row["timestamp_utc"],
                    "epoch_utc": row["epoch_utc"],
                    "heart_rate_bpm": row["heart_rate_bpm"],
                    "session_id": row["session_id"],
                    "source": row["source"],
                    "quality_flags": quality,
                }
            )
        return {
            "minutes": minutes,
            "points": points,
            "disconnects": _disconnect_intervals(db(), cutoff),
        }

    @app.get("/api/sessions")
    def sessions(limit: int = Query(default=50, ge=1, le=500)) -> list[dict]:
        return db().sessions(limit=limit)

    @app.get("/api/events")
    def events(limit: int = Query(default=100, ge=1, le=1000)) -> list[dict]:
        return db().events(limit=limit)

    @app.get("/api/annotations")
    def annotations() -> list[dict]:
        return db().annotations()

    @app.post("/api/battery", status_code=201)
    def log_battery(payload: BatteryIn) -> dict[str, Any]:
        event_id = db().add_event(
            "battery_reading",
            details={
                "percent": payload.percent,
                "note": payload.note,
                "source": "manual",
            },
        )
        return {
            "event_id": event_id,
            "percent": payload.percent,
            "recorded_at": iso_utc(),
        }

    @app.get("/api/battery")
    def battery_readings(
        limit: int = Query(default=200, ge=1, le=2000),
    ) -> list[dict[str, Any]]:
        readings = []
        for event in db().events(limit=limit, event_types=["battery_reading"]):
            try:
                details = json.loads(event["details"] or "{}")
            except json.JSONDecodeError:
                continue
            readings.append(
                {
                    "event_id": event["event_id"],
                    "recorded_at": event["event_time_utc"],
                    "percent": details.get("percent"),
                    "note": details.get("note"),
                }
            )
        return readings

    @app.get("/api/analytics")
    def analytics(
        range_key: str = Query(default="current_session", alias="range"),
        start: str | None = None,
        end: str | None = None,
        session_id: int | None = None,
        include_empty: bool | None = None,
        include_simulated: bool = False,
        bin_width: float = Query(default=5.0, ge=1.0, le=50.0),
        bands: str | None = None,
        tz_name: str = Query(default=DEFAULT_TIMEZONE, alias="tz"),
    ) -> dict[str, Any]:
        """Read-only descriptive statistics for the selected range."""
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError as exc:
            raise HTTPException(status_code=400, detail="unknown timezone") from exc
        try:
            band_spec = parse_bands(bands)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        path = db().path
        session = load_session_row(path, session_id=session_id)
        try:
            resolved = resolve_range(
                range_key,
                start=start,
                end=end,
                session=session,
                tz=tz,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        query_session_id = session_id
        if (
            query_session_id is None
            and resolved["kind"] == "current_session"
            and session is not None
        ):
            query_session_id = int(session["session_id"])
        if query_session_id is not None:
            resolved["session_id"] = query_session_id

        frame = load_measurement_frame(
            path,
            start=resolved["start_utc"],
            end=resolved["end_utc"],
            session_id=query_session_id,
            include_simulated=include_simulated,
            tz=tz,
        )
        events = load_events_frame(
            path,
            start=resolved["start_utc"],
            end=resolved["end_utc"],
            event_types=["disconnected"],
            tz=tz,
        )
        summary = summary_block(frame, resolved)
        if include_empty is None:
            include_empty = resolved["duration_seconds"] <= 48 * 3600
        hourly = hourly_table(frame, resolved, tz=tz, include_empty=bool(include_empty))
        daily = daily_table(frame, events, resolved, tz=tz)
        annotations = load_annotations(path, local_tz=tz)
        sleep = sleep_report(
            frame,
            annotations,
            tz=tz,
            start=resolved["start_utc"],
            end=resolved["end_utc"],
        )
        return {
            "range": resolved,
            "summary": summary,
            "hourly": hourly,
            "daily": daily,
            "distribution": distribution_report(
                frame["heart_rate_bpm"], hourly, bin_width=bin_width
            ),
            "bands": band_report(frame, band_spec),
            "sleep": sleep,
            "heatmap": heatmap_report(frame, tz=tz),
            "baseline": baseline_report(
                frame, sleep.get("history", []), tz=tz
            ),
            "warnings": summary["warnings"],
            "computed_at": iso_utc(),
        }

    @app.get("/api/analytics/trajectory")
    def analytics_trajectory(
        start: str,
        end: str,
        session_id: int | None = None,
        include_simulated: bool = False,
        tz_name: str = Query(default=DEFAULT_TIMEZONE, alias="tz"),
    ) -> dict[str, Any]:
        """Raw HR points for an hourly/day drill-down."""
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError as exc:
            raise HTTPException(status_code=400, detail="unknown timezone") from exc
        try:
            resolved = resolve_range("custom", start=start, end=end, tz=tz)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        path = db().path
        frame = load_measurement_frame(
            path,
            start=resolved["start_utc"],
            end=resolved["end_utc"],
            session_id=session_id,
            include_simulated=include_simulated,
            tz=tz,
        )
        return {
            "range": resolved,
            "summary": summary_block(frame, resolved),
            "points": trajectory_points(frame),
            "computed_at": iso_utc(),
        }

    @app.post("/api/annotations", status_code=201)
    def create_annotation(payload: AnnotationIn) -> dict[str, Any]:
        try:
            annotation_id = db().add_annotation(**payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"annotation_id": annotation_id}

    @app.patch("/api/annotations/{annotation_id}")
    def patch_annotation(annotation_id: int, payload: AnnotationPatch) -> dict[str, Any]:
        changes = {k: v for k, v in payload.model_dump().items() if v is not None}
        try:
            ok = db().update_annotation(annotation_id, **changes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not ok:
            raise HTTPException(status_code=404, detail="annotation not found")
        return {"updated": True}

    @app.delete("/api/annotations/{annotation_id}")
    def delete_annotation(annotation_id: int) -> dict[str, Any]:
        if not db().delete_annotation(annotation_id):
            raise HTTPException(status_code=404, detail="annotation not found")
        return {"deleted": True}

    @app.post("/api/control")
    def control(payload: ControlIn) -> dict[str, Any]:
        action = payload.action
        if action == "restart":
            if not app.state.restart_allowed:
                raise HTTPException(status_code=403, detail="restart is not enabled")
            try:
                result = subprocess.run(
                    ["systemctl", "--user", "restart", app.state.unit],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            if result.returncode != 0:
                raise HTTPException(
                    status_code=500, detail=result.stderr.strip() or "restart failed"
                )
            return {"action": action, "ok": True}
        try:
            state = apply_action(control_path, action)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"action": action, "paused": state.paused, "force_reconnect": state.force_reconnect}

    @app.get("/api/export.csv")
    def export_csv() -> Response:
        rows = db().measurements_between(None, None)
        buffer = io.StringIO()
        if rows:
            writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return Response(
            content=buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="band9_raw_measurements.csv"'},
        )

    @app.websocket("/ws/hr")
    async def ws_hr(websocket: WebSocket, minutes: float = 5.0) -> None:
        await websocket.accept()
        try:
            while True:
                cutoff = datetime.now(tz=UTC).timestamp() - minutes * 60.0
                rows = db().recent_measurements(minutes=minutes, limit=50000)
                await websocket.send_json(
                    {
                        "minutes": minutes,
                        "points": rows,
                        "disconnects": _disconnect_intervals(db(), cutoff),
                    }
                )
                await asyncio.sleep(1.0)
        except WebSocketDisconnect:
            return
        except Exception:  # noqa: BLE001 - the browser may close at any time
            return

    return app


app = create_app()
