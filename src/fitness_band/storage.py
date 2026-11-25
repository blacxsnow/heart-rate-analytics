"""Local persistence: SQLite for measurements and raw packets, plus exporters.

The database is intentionally device-agnostic. A metric is identified by a
normalised name (``heart_rate``, ``spo2`` ...) and unit, so downstream tools do
not need to understand the Huawei protocol.
"""

from __future__ import annotations

import csv
import json
import sqlite3
import threading
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS devices (
    address       TEXT PRIMARY KEY,
    name          TEXT,
    model         TEXT,
    firmware      TEXT,
    first_seen    REAL NOT NULL,
    last_seen     REAL NOT NULL,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_address  TEXT,
    started_at      REAL NOT NULL,
    ended_at        REAL,
    source          TEXT NOT NULL,
    notes           TEXT,
    FOREIGN KEY (device_address) REFERENCES devices(address)
);

CREATE TABLE IF NOT EXISTS measurements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER,
    device_address  TEXT,
    ts_utc          REAL NOT NULL,
    ts_iso          TEXT NOT NULL,
    metric          TEXT NOT NULL,
    value           REAL NOT NULL,
    unit            TEXT NOT NULL,
    source          TEXT NOT NULL,
    quality         TEXT,
    raw_hex         TEXT,
    meta_json       TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_measurements_metric_ts
    ON measurements(metric, ts_utc);
CREATE INDEX IF NOT EXISTS idx_measurements_device_ts
    ON measurements(device_address, ts_utc);

CREATE TABLE IF NOT EXISTS raw_packets (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     INTEGER,
    ts_utc         REAL NOT NULL,
    ts_iso         TEXT NOT NULL,
    direction      TEXT NOT NULL,
    characteristic TEXT,
    data_hex       TEXT NOT NULL,
    note           TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_raw_packets_ts ON raw_packets(ts_utc);

CREATE TABLE IF NOT EXISTS events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc    REAL NOT NULL,
    ts_iso    TEXT NOT NULL,
    level     TEXT NOT NULL,
    message   TEXT NOT NULL,
    meta_json TEXT
);
"""


def iso_utc(ts: float | None = None) -> str:
    ts = time.time() if ts is None else ts
    return datetime.fromtimestamp(ts, tz=UTC).isoformat(timespec="milliseconds")


class SQLiteStore:
    """Small, dependency-free time-series store.

    SQLite is a reasonable first target for one Band 9 (a few measurements per
    second). If the project later needs multi-device, high-rate ingestion, the
    same interface can be backed by TimescaleDB/InfluxDB.
    """

    def __init__(self, path: str | Path = "data/band9.sqlite3") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
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

    # --- devices / sessions ------------------------------------------------
    def upsert_device(
        self,
        address: str,
        name: str | None = None,
        model: str | None = None,
        firmware: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = time.time()
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO devices(address, name, model, firmware, first_seen, last_seen, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(address) DO UPDATE SET
                    name=COALESCE(excluded.name, devices.name),
                    model=COALESCE(excluded.model, devices.model),
                    firmware=COALESCE(excluded.firmware, devices.firmware),
                    last_seen=excluded.last_seen,
                    metadata_json=COALESCE(excluded.metadata_json, devices.metadata_json)
                """,
                (
                    address,
                    name,
                    model,
                    firmware,
                    now,
                    now,
                    json.dumps(metadata, sort_keys=True) if metadata else None,
                ),
            )

    def start_session(self, device_address: str | None, source: str, notes: str | None = None) -> int:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO sessions(device_address, started_at, source, notes) VALUES (?, ?, ?, ?)",
                (device_address, time.time(), source, notes),
            )
            return int(cur.lastrowid)

    def end_session(self, session_id: int) -> None:
        with self._cursor() as cur:
            cur.execute("UPDATE sessions SET ended_at=? WHERE id=? AND ended_at IS NULL", (time.time(), session_id))

    # --- measurements ------------------------------------------------------
    def add_measurement(
        self,
        *,
        metric: str,
        value: float,
        unit: str,
        source: str,
        device_address: str | None = None,
        session_id: int | None = None,
        ts: float | None = None,
        quality: str | None = None,
        raw: bytes | None = None,
        meta: dict[str, Any] | None = None,
    ) -> int:
        ts = time.time() if ts is None else ts
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO measurements(
                    session_id, device_address, ts_utc, ts_iso, metric, value, unit,
                    source, quality, raw_hex, meta_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    device_address,
                    ts,
                    iso_utc(ts),
                    metric,
                    float(value),
                    unit,
                    source,
                    quality,
                    raw.hex() if raw is not None else None,
                    json.dumps(meta, sort_keys=True) if meta else None,
                ),
            )
            return int(cur.lastrowid)

    def add_measurements(self, rows: Iterable[dict[str, Any]]) -> int:
        count = 0
        with self._cursor() as cur:
            for row in rows:
                ts = row.get("ts", time.time())
                raw = row.get("raw")
                cur.execute(
                    """
                    INSERT INTO measurements(
                        session_id, device_address, ts_utc, ts_iso, metric, value, unit,
                        source, quality, raw_hex, meta_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row.get("session_id"),
                        row.get("device_address"),
                        ts,
                        iso_utc(ts),
                        row["metric"],
                        float(row["value"]),
                        row["unit"],
                        row["source"],
                        row.get("quality"),
                        raw.hex() if isinstance(raw, (bytes, bytearray)) else raw,
                        json.dumps(row["meta"], sort_keys=True) if row.get("meta") else None,
                    ),
                )
                count += 1
        return count

    # --- raw packets / events ---------------------------------------------
    def add_raw_packet(
        self,
        *,
        direction: str,
        characteristic: str | None,
        data: bytes,
        session_id: int | None = None,
        ts: float | None = None,
        note: str | None = None,
    ) -> int:
        ts = time.time() if ts is None else ts
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO raw_packets(session_id, ts_utc, ts_iso, direction, characteristic, data_hex, note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, ts, iso_utc(ts), direction, characteristic, data.hex(), note),
            )
            return int(cur.lastrowid)

    def add_event(self, level: str, message: str, meta: dict[str, Any] | None = None) -> None:
        now = time.time()
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO events(ts_utc, ts_iso, level, message, meta_json) VALUES (?, ?, ?, ?, ?)",
                (now, iso_utc(now), level, message, json.dumps(meta, sort_keys=True) if meta else None),
            )

    # --- queries / export --------------------------------------------------
    def query_measurements(
        self,
        metric: str | None = None,
        start: float | None = None,
        end: float | None = None,
        limit: int = 10000,
    ) -> list[sqlite3.Row]:
        sql = "SELECT * FROM measurements WHERE 1=1"
        params: list[Any] = []
        if metric:
            sql += " AND metric=?"
            params.append(metric)
        if start is not None:
            sql += " AND ts_utc>=?"
            params.append(start)
        if end is not None:
            sql += " AND ts_utc<=?"
            params.append(end)
        sql += " ORDER BY ts_utc ASC LIMIT ?"
        params.append(limit)
        with self._lock:
            return list(self._conn.execute(sql, params).fetchall())

    def summary(self) -> dict[str, Any]:
        with self._lock:
            metrics = [
                dict(row)
                for row in self._conn.execute(
                    """
                    SELECT metric, unit, COUNT(*) AS n, MIN(ts_utc) AS first_ts, MAX(ts_utc) AS last_ts,
                           MIN(value) AS min_value, MAX(value) AS max_value, AVG(value) AS mean_value
                    FROM measurements GROUP BY metric, unit ORDER BY metric
                    """
                )
            ]
            devices = [dict(row) for row in self._conn.execute("SELECT * FROM devices")]
            sessions = [dict(row) for row in self._conn.execute("SELECT * FROM sessions ORDER BY id DESC LIMIT 20")]
            raw_count = self._conn.execute("SELECT COUNT(*) FROM raw_packets").fetchone()[0]
        return {"metrics": metrics, "devices": devices, "sessions": sessions, "raw_packets": raw_count}

    def export_csv(self, path: str | Path, metric: str | None = None) -> int:
        rows = self.query_measurements(metric=metric, limit=10_000_000)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                ["ts_utc", "ts_iso", "device_address", "metric", "value", "unit", "source", "quality", "raw_hex"]
            )
            for row in rows:
                writer.writerow(
                    [
                        row["ts_utc"],
                        row["ts_iso"],
                        row["device_address"],
                        row["metric"],
                        row["value"],
                        row["unit"],
                        row["source"],
                        row["quality"],
                        row["raw_hex"],
                    ]
                )
        return len(rows)

    def export_jsonl(self, path: str | Path, metric: str | None = None) -> int:
        rows = self.query_measurements(metric=metric, limit=10_000_000)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(dict(row), sort_keys=True) + "\n")
        return len(rows)
