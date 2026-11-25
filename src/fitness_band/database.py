"""SQLite schema and store for the long-running acquisition service.

This is intentionally separate from :mod:`fitness_band.storage` (the original
exploration store). The acquisition service owns one database and writes only
append-only observations plus session/event metadata; the analysis application
opens it read-only.
"""

from __future__ import annotations

import csv
import json
import sqlite3
import threading
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Self

SCHEMA_VERSION = 1

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;

CREATE TABLE IF NOT EXISTS schema_meta (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS monitoring_sessions (
    session_id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time                  TEXT NOT NULL,
    end_time                    TEXT,
    connection_status           TEXT NOT NULL,
    total_measurements          INTEGER NOT NULL DEFAULT 0,
    expected_sampling_interval  REAL,
    actual_sampling_interval    REAL,
    disconnect_count            INTEGER NOT NULL DEFAULT 0,
    session_metadata            TEXT
);

CREATE TABLE IF NOT EXISTS raw_measurements (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc           TEXT NOT NULL,
    received_at_utc         TEXT NOT NULL,
    monotonic_timestamp     REAL NOT NULL,
    heart_rate_bpm          INTEGER NOT NULL,
    device_id               TEXT NOT NULL,
    session_id              INTEGER,
    source                  TEXT NOT NULL,
    raw_payload             TEXT,
    quality_flags           TEXT,
    tz_offset_minutes       INTEGER,
    measurement_time_known  INTEGER NOT NULL DEFAULT 0,
    epoch_utc               REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES monitoring_sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_raw_measurements_time
    ON raw_measurements(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_raw_measurements_epoch
    ON raw_measurements(epoch_utc);
CREATE INDEX IF NOT EXISTS idx_raw_measurements_session
    ON raw_measurements(session_id);

CREATE TABLE IF NOT EXISTS device_events (
    event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    event_time_utc  TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    session_id      INTEGER,
    details         TEXT,
    FOREIGN KEY (session_id) REFERENCES monitoring_sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_device_events_time
    ON device_events(event_time_utc);
CREATE INDEX IF NOT EXISTS idx_device_events_type
    ON device_events(event_type);

CREATE TABLE IF NOT EXISTS annotations (
    annotation_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type     TEXT NOT NULL,
    start_time     TEXT NOT NULL,
    end_time       TEXT NOT NULL,
    confidence     REAL,
    notes          TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_annotations_type
    ON annotations(event_type, start_time);
"""


def iso_utc(ts: float | None = None) -> str:
    ts = time.time() if ts is None else ts
    return datetime.fromtimestamp(ts, tz=UTC).isoformat(timespec="milliseconds")


def parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class AcquisitionDB:
    """Thread-safe append-oriented SQLite store for the acquisition daemon."""

    def __init__(self, path: str | Path = "data/acquisition.sqlite3") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            row = self._conn.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
            if row is None:
                self._conn.execute("INSERT INTO schema_meta(version) VALUES (?)", (SCHEMA_VERSION,))
            elif int(row["version"]) != SCHEMA_VERSION:
                raise RuntimeError(
                    f"unsupported database schema {row['version']} (expected {SCHEMA_VERSION})"
                )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            finally:
                cur.close()

    # --- sessions ----------------------------------------------------------
    def start_session(
        self,
        *,
        device_id: str,
        expected_sampling_interval: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        now = iso_utc()
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO monitoring_sessions(
                    start_time, connection_status, expected_sampling_interval, session_metadata
                ) VALUES (?, ?, ?, ?)
                """,
                (now, "starting", expected_sampling_interval, _json(metadata)),
            )
            return int(cur.lastrowid)

    def end_session(
        self,
        session_id: int,
        *,
        status: str,
        actual_sampling_interval: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                UPDATE monitoring_sessions
                   SET end_time=?, connection_status=?, actual_sampling_interval=?,
                       session_metadata=COALESCE(?, session_metadata)
                 WHERE session_id=?
                """,
                (iso_utc(), status, actual_sampling_interval, _json(metadata), session_id),
            )

    def set_session_status(self, session_id: int, status: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE monitoring_sessions SET connection_status=? WHERE session_id=?",
                (status, session_id),
            )

    def update_session_stats(
        self,
        session_id: int,
        *,
        actual_sampling_interval: float | None = None,
        disconnect_count: int | None = None,
    ) -> None:
        with self._cursor() as cur:
            if actual_sampling_interval is not None:
                cur.execute(
                    "UPDATE monitoring_sessions SET actual_sampling_interval=? WHERE session_id=?",
                    (actual_sampling_interval, session_id),
                )
            if disconnect_count is not None:
                cur.execute(
                    "UPDATE monitoring_sessions SET disconnect_count=? WHERE session_id=?",
                    (disconnect_count, session_id),
                )

    def recover_open_sessions(self, *, reason: str = "process_restart") -> list[int]:
        """Close sessions left open by a crash/reboot and record why."""
        now = iso_utc()
        recovered: list[int] = []
        with self._cursor() as cur:
            rows = cur.execute(
                "SELECT session_id FROM monitoring_sessions WHERE end_time IS NULL"
            ).fetchall()
            for row in rows:
                sid = int(row["session_id"])
                recovered.append(sid)
                cur.execute(
                    """
                    UPDATE monitoring_sessions
                       SET end_time=?, connection_status='interrupted'
                     WHERE session_id=? AND end_time IS NULL
                    """,
                    (now, sid),
                )
                cur.execute(
                    """
                    INSERT INTO device_events(event_time_utc, event_type, session_id, details)
                    VALUES (?, 'session_interrupted', ?, ?)
                    """,
                    (now, sid, _json({"reason": reason})),
                )
        return recovered

    # --- observations ------------------------------------------------------
    def add_measurement(
        self,
        *,
        heart_rate_bpm: int,
        device_id: str,
        session_id: int | None,
        timestamp_utc: str,
        received_at_utc: str,
        monotonic_timestamp: float,
        epoch_utc: float,
        source: str = "ble_hrs",
        raw_payload: str | None = None,
        quality_flags: dict[str, Any] | None = None,
        tz_offset_minutes: int | None = None,
        measurement_time_known: bool = False,
    ) -> int:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO raw_measurements(
                    timestamp_utc, received_at_utc, monotonic_timestamp, heart_rate_bpm,
                    device_id, session_id, source, raw_payload, quality_flags,
                    tz_offset_minutes, measurement_time_known, epoch_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp_utc,
                    received_at_utc,
                    monotonic_timestamp,
                    int(heart_rate_bpm),
                    device_id,
                    session_id,
                    source,
                    raw_payload,
                    _json(quality_flags),
                    tz_offset_minutes,
                    1 if measurement_time_known else 0,
                    epoch_utc,
                ),
            )
            measurement_id = int(cur.lastrowid)
            if session_id is not None:
                cur.execute(
                    """
                    UPDATE monitoring_sessions
                       SET total_measurements = total_measurements + 1
                     WHERE session_id=?
                    """,
                    (session_id,),
                )
            return measurement_id

    def add_measurements(self, rows: Iterable[dict[str, Any]]) -> int:
        count = 0
        for row in rows:
            self.add_measurement(**row)
            count += 1
        return count

    def add_event(
        self,
        event_type: str,
        *,
        session_id: int | None = None,
        details: dict[str, Any] | None = None,
        ts: float | None = None,
    ) -> int:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO device_events(event_time_utc, event_type, session_id, details)
                VALUES (?, ?, ?, ?)
                """,
                (iso_utc(ts), event_type, session_id, _json(details)),
            )
            return int(cur.lastrowid)

    # --- annotations -------------------------------------------------------
    def add_annotation(
        self,
        *,
        event_type: str,
        start_time: str,
        end_time: str,
        confidence: float | None = None,
        notes: str | None = None,
    ) -> int:
        start, end = normalize_interval(start_time, end_time)
        start_time = start.isoformat(timespec="seconds")
        end_time = end.isoformat(timespec="seconds")
        now = iso_utc()
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO annotations(
                    event_type, start_time, end_time, confidence, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_type, start_time, end_time, confidence, notes, now, now),
            )
            return int(cur.lastrowid)

    def update_annotation(
        self,
        annotation_id: int,
        *,
        event_type: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        confidence: float | None = None,
        notes: str | None = None,
    ) -> bool:
        fields: list[str] = []
        values: list[Any] = []
        for column, value in (
            ("event_type", event_type),
            ("start_time", start_time),
            ("end_time", end_time),
            ("confidence", confidence),
            ("notes", notes),
        ):
            if value is not None:
                fields.append(f"{column}=?")
                values.append(value)
        if not fields:
            return False
        fields.append("updated_at=?")
        values.append(iso_utc())
        values.append(annotation_id)
        with self._cursor() as cur:
            cur.execute(f"UPDATE annotations SET {', '.join(fields)} WHERE annotation_id=?", values)
            return cur.rowcount > 0

    def delete_annotation(self, annotation_id: int) -> bool:
        with self._cursor() as cur:
            cur.execute("DELETE FROM annotations WHERE annotation_id=?", (annotation_id,))
            return cur.rowcount > 0

    # --- reads -------------------------------------------------------------
    def recent_measurements(self, *, minutes: float = 5.0, limit: int = 10000) -> list[dict]:
        cutoff = time.time() - minutes * 60.0
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, timestamp_utc, received_at_utc, epoch_utc, heart_rate_bpm,
                       session_id, device_id, source, raw_payload, quality_flags
                  FROM raw_measurements
                 WHERE epoch_utc >= ?
                 ORDER BY epoch_utc ASC
                 LIMIT ?
                """,
                (cutoff, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def measurements_between(self, start: str | None, end: str | None) -> list[dict]:
        sql = "SELECT * FROM raw_measurements WHERE 1=1"
        params: list[Any] = []
        if start:
            sql += " AND timestamp_utc >= ?"
            params.append(start)
        if end:
            sql += " AND timestamp_utc < ?"
            params.append(end)
        sql += " ORDER BY timestamp_utc ASC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def sessions(self, *, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM monitoring_sessions ORDER BY session_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def events(self, *, limit: int = 100, event_types: list[str] | None = None) -> list[dict]:
        sql = "SELECT * FROM device_events"
        params: list[Any] = []
        if event_types:
            placeholders = ",".join("?" for _ in event_types)
            sql += f" WHERE event_type IN ({placeholders})"
            params.extend(event_types)
        sql += " ORDER BY event_id DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def annotations(self, *, limit: int = 500) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM annotations ORDER BY start_time DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> dict:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) AS n FROM raw_measurements").fetchone()["n"]
            first = self._conn.execute(
                "SELECT MIN(timestamp_utc) AS v FROM raw_measurements"
            ).fetchone()["v"]
            last = self._conn.execute(
                "SELECT MAX(timestamp_utc) AS v FROM raw_measurements"
            ).fetchone()["v"]
            sessions = self._conn.execute(
                "SELECT COUNT(*) AS n FROM monitoring_sessions"
            ).fetchone()["n"]
            events = self._conn.execute("SELECT COUNT(*) AS n FROM device_events").fetchone()["n"]
            annotations = self._conn.execute("SELECT COUNT(*) AS n FROM annotations").fetchone()[
                "n"
            ]
        size = (
            Path(self.path).stat().st_size
            if self.path != ":memory:" and Path(self.path).exists()
            else 0
        )
        return {
            "total_measurements": int(total),
            "first_measurement": first,
            "last_measurement": last,
            "sessions": int(sessions),
            "events": int(events),
            "annotations": int(annotations),
            "database_bytes": size,
        }

    def export_csv(self, path: str | Path) -> int:
        rows = self.measurements_between(None, None)
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else [])
            if rows:
                writer.writeheader()
                writer.writerows(rows)
        return len(rows)


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True, default=str)


def normalize_interval(start_time: str, end_time: str) -> tuple[datetime, datetime]:
    """Return a UTC interval; an end at/before the start means the next day."""

    start = parse_iso(start_time)
    end = parse_iso(end_time)
    if end <= start:
        end += timedelta(days=1)
    if (end - start).total_seconds() > 48 * 3600:
        raise ValueError("annotation interval is longer than 48 hours")
    return start, end


__all__ = [
    "SCHEMA",
    "SCHEMA_VERSION",
    "AcquisitionDB",
    "iso_utc",
    "normalize_interval",
    "parse_iso",
]
