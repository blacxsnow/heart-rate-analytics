"""Runtime state shared with the read-only web dashboard."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

DEFAULT_STATE: dict[str, Any] = {
    "service_status": "starting",
    "connection_status": "disconnected",
    "current_hr": None,
    "current_hr_at": None,
    "last_measurement_at": None,
    "last_measurement_epoch": None,
    "last_connection_at": None,
    "last_disconnection_at": None,
    "reconnect_attempts": 0,
    "consecutive_failures": 0,
    "next_retry_at": None,
    "session_id": None,
    "session_started_at": None,
    "total_measurements": 0,
    "sampling_interval_s": None,
    "expected_sampling_interval_s": None,
    "adapter_available": None,
    "band_visible": None,
    "hr_broadcast_active": None,
    "last_error": None,
    "device_id": None,
    "device_name": None,
    "paused": False,
    "started_at": None,
    "updated_at": None,
}


class StateWriter:
    """Atomic, throttled writer for the daemon's status snapshot."""

    def __init__(self, path: str | Path, *, min_interval: float = 0.4) -> None:
        self.path = Path(path)
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._state = dict(DEFAULT_STATE)
        self._last_write = 0.0

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def update(self, *, force: bool = False, **fields: Any) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            self._state.update(fields)
            self._state["updated_at"] = now
            if not force and now - self._last_write < self.min_interval:
                return dict(self._state)
            self._last_write = now
            payload = dict(self._state)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)
        return payload


def read_state(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return dict(DEFAULT_STATE)
    return {**DEFAULT_STATE, **raw}


__all__ = ["DEFAULT_STATE", "StateWriter", "read_state"]
