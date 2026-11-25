"""Synthetic acquisition source for UI/analysis development.

Records produced here are explicitly marked ``source='simulated'`` and
``quality_flags.simulated=true``. They must never be mixed with real data in the
production database.
"""

from __future__ import annotations

import asyncio
import math
import random
import time

from ..database import AcquisitionDB
from .control import read_control
from .spool import SpoolQueue
from .state import StateWriter
from .timestamping import now_observation


class SimulatedCollector:
    def __init__(
        self,
        *,
        db: AcquisitionDB,
        state: StateWriter,
        spool: SpoolQueue,
        control_path: str,
        interval: float = 1.0,
    ) -> None:
        self.db = db
        self.state = state
        self.spool = spool
        self.control_path = control_path
        self.interval = interval
        self._stop = asyncio.Event()
        self._session_id: int | None = None

    def stop(self) -> None:
        self._stop.set()

    async def run(self, duration: float | None = None) -> None:
        assert self.db is not None
        self._session_id = self.db.start_session(
            device_id="simulated",
            expected_sampling_interval=self.interval,
            metadata={"mode": "simulation", "simulated": True},
        )
        self.db.add_event(
            "monitoring_started", session_id=self._session_id, details={"simulated": True}
        )
        self.db.set_session_status(self._session_id, "connected")
        assert isinstance(self.state, StateWriter)
        self.state.update(
            force=True,
            service_status="running",
            connection_status="connected",
            device_id="simulated",
            device_name="Simulated Band 9",
            session_id=self._session_id,
            session_started_at=time.time(),
            last_connection_at=time.time(),
            expected_sampling_interval_s=self.interval,
            started_at=time.time(),
            paused=False,
        )
        started = time.monotonic()
        count = 0
        try:
            while not self._stop.is_set():
                if duration is not None and time.monotonic() - started >= duration:
                    break
                control = read_control(self.control_path)
                if control.paused:
                    self.state.update(connection_status="paused", paused=True)
                    await self._sleep(1.0)
                    continue
                observed = now_observation()
                elapsed = time.monotonic() - started
                value = round(
                    72.0
                    + 6.0 * math.sin(elapsed / 90.0)
                    + 2.0 * math.sin(elapsed / 13.0)
                    + random.gauss(0.0, 0.8)
                )
                value = max(48, min(120, value))
                record = {
                    "heart_rate_bpm": value,
                    "device_id": "simulated",
                    "session_id": self._session_id,
                    "timestamp_utc": observed.utc_iso,
                    "received_at_utc": observed.utc_iso,
                    "monotonic_timestamp": observed.monotonic,
                    "epoch_utc": observed.epoch,
                    "source": "simulated",
                    "raw_payload": None,
                    "quality_flags": {
                        "simulated": True,
                        "measurement_time_known": False,
                        "sensor_contact": True,
                    },
                    "tz_offset_minutes": observed.tz_offset_minutes,
                    "measurement_time_known": False,
                }
                try:
                    self.db.add_measurement(**record)
                except Exception:  # noqa: BLE001 - spool instead of losing the observation
                    self.spool.enqueue(record)
                count += 1
                self.state.update(
                    current_hr=value,
                    current_hr_at=observed.epoch,
                    last_measurement_at=observed.utc_iso,
                    last_measurement_epoch=observed.epoch,
                    total_measurements=count,
                    sampling_interval_s=self.interval,
                    connection_status="connected",
                )
                if not await self._sleep(self.interval):
                    break
        finally:
            self.db.end_session(
                self._session_id,
                status="stopped",
                actual_sampling_interval=self.interval,
            )
            self.db.add_event(
                "monitoring_stopped", session_id=self._session_id, details={"simulated": True}
            )
            self.state.update(
                force=True,
                service_status="stopped",
                connection_status="stopped",
                paused=False,
            )

    async def _sleep(self, seconds: float) -> bool:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
            return False
        except TimeoutError:
            return True


__all__ = ["SimulatedCollector"]
