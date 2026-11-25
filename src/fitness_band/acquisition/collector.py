"""Continuous BLE Heart Rate Service collector with reconnect/watchdog logic."""

from __future__ import annotations

import asyncio
import logging
import random
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

from bleak import BleakClient
from bleak.exc import BleakError

from ..ble_scanner import find_endpoint
from ..database import AcquisitionDB
from ..hrs import HeartRateParseError, parse_heart_rate_measurement
from .control import ControlState, read_control
from .spool import SpoolQueue
from .state import StateWriter
from .timestamping import now_observation

LOG = logging.getLogger("band9.acquisition")
HRS_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb"
HRS_CHAR = "00002a37-0000-1000-8000-00805f9b34fb"


@dataclass
class CollectorConfig:
    address: str | None = None
    scan_timeout: float = 12.0
    connect_timeout: float = 30.0
    stale_timeout: float = 15.0
    expected_interval: float = 1.0
    backoff_initial: float = 2.0
    backoff_max: float = 60.0
    stable_after: float = 15.0
    spool_drain_interval: float = 60.0


@dataclass
class ConnectionResult:
    reason: str
    duration: float
    packets: int


class BandHRCollector:
    def __init__(
        self,
        *,
        db: AcquisitionDB,
        state: StateWriter,
        spool: SpoolQueue,
        control_path: str | Path,
        config: CollectorConfig | None = None,
    ) -> None:
        self.db = db
        self.state = state
        self.spool = spool
        self.control_path = Path(control_path)
        self.config = config or CollectorConfig()
        self._stop = asyncio.Event()
        self._session_id: int | None = None
        self._session_packets = 0
        self._session_started = 0.0
        self._last_packet_monotonic: float | None = None
        self._intervals: list[float] = []
        self._last_control = ControlState()
        self._last_force_seen = 0
        self._last_spool_drain = 0.0
        self._last_scan_event = 0.0
        self._failures = 0
        self._attempts = 0
        self._disconnects = 0
        self._paused_event_logged = False

    def stop(self) -> None:
        self._stop.set()

    # --- helpers -----------------------------------------------------------
    def _backoff_seconds(self) -> float:
        exponent = max(0, self._failures - 1)
        base = min(self.config.backoff_initial * (2**exponent), self.config.backoff_max)
        return base + random.uniform(0.0, 1.0)

    def _sample_interval(self) -> float | None:
        if len(self._intervals) < 2:
            return None
        return round(statistics.median(self._intervals[-30:]), 3)

    def _control(self) -> ControlState:
        state = read_control(self.control_path)
        self._last_control = state
        return state

    def _set_connected(self, *, endpoint_name: str | None, endpoint_address: str) -> None:
        self.state.update(
            force=True,
            connection_status="connected",
            last_connection_at=time.time(),
            device_id=endpoint_address,
            device_name=endpoint_name,
            last_error=None,
            adapter_available=True,
            next_retry_at=None,
            consecutive_failures=0,
        )

    def _handle_packet(self, data: bytes) -> None:
        observed = now_observation()
        try:
            measurement = parse_heart_rate_measurement(data)
        except HeartRateParseError as exc:
            try:
                self.db.add_event(
                    "parse_error",
                    session_id=self._session_id,
                    details={"error": str(exc), "raw_payload": bytes(data).hex()},
                )
            except Exception:
                LOG.exception("could not record parse error")
            self.state.update(last_error=f"parse_error: {exc}")
            LOG.warning("heart-rate parse error: %s raw=%s", exc, bytes(data).hex())
            return

        quality = {
            "flags": measurement.flags,
            "sensor_contact": measurement.sensor_contact,
            "measurement_time_known": False,
            "time_source": "pc_reception",
            "tz_offset_minutes": observed.tz_offset_minutes,
        }
        record = {
            "heart_rate_bpm": measurement.heart_rate_bpm,
            "device_id": self.state.snapshot().get("device_id") or "unknown",
            "session_id": self._session_id,
            "timestamp_utc": observed.utc_iso,
            "received_at_utc": observed.utc_iso,
            "monotonic_timestamp": observed.monotonic,
            "epoch_utc": observed.epoch,
            "source": "ble_hrs",
            "raw_payload": bytes(data).hex(),
            "quality_flags": quality,
            "tz_offset_minutes": observed.tz_offset_minutes,
            "measurement_time_known": False,
        }
        try:
            self.db.add_measurement(**record)
        except Exception as exc:  # noqa: BLE001 - never drop an observation
            try:
                self.spool.enqueue(record)
            except Exception:
                LOG.exception("could not spool observation")
            try:
                self.db.add_event(
                    "db_write_deferred",
                    session_id=self._session_id,
                    details={"error": str(exc), "heart_rate_bpm": measurement.heart_rate_bpm},
                )
            except Exception:
                LOG.debug("could not record deferred-write event", exc_info=True)
            LOG.error("database write failed, spooled observation: %s", exc)

        previous = getattr(self, "_previous_monotonic", None)
        if previous is not None:
            delta = observed.monotonic - previous
            if 0 < delta < 10:
                self._intervals.append(delta)
        self._previous_monotonic = observed.monotonic
        self._last_packet_monotonic = observed.monotonic
        self._session_packets += 1

        interval = self._sample_interval()
        self.state.update(
            current_hr=measurement.heart_rate_bpm,
            current_hr_at=observed.epoch,
            last_measurement_at=observed.utc_iso,
            last_measurement_epoch=observed.epoch,
            total_measurements=self._session_packets,
            sampling_interval_s=interval,
            connection_status="connected",
        )
        if self._session_packets % 15 == 0 and self._session_id is not None:
            self.db.update_session_stats(self._session_id, actual_sampling_interval=interval)

    # --- connection --------------------------------------------------------
    async def _connect_and_stream(self) -> ConnectionResult:
        assert self._session_id is not None
        disconnected = asyncio.Event()
        self.state.update(connection_status="connecting", force=True)
        started = time.monotonic()
        start_packets = self._session_packets

        def on_disconnect(_client: BleakClient) -> None:
            disconnected.set()

        endpoint = await self._find_endpoint()
        if endpoint is None:
            raise RuntimeError("HR broadcast endpoint not found")

        client = BleakClient(
            endpoint.address,
            timeout=self.config.connect_timeout,
            disconnected_callback=on_disconnect,
        )
        try:
            await client.connect()
            self.db.add_event(
                "connected",
                session_id=self._session_id,
                details={"address": endpoint.address, "name": endpoint.name},
            )
            self._set_connected(endpoint_name=endpoint.name, endpoint_address=endpoint.address)
            LOG.info("connected to %s (%s)", endpoint.name, endpoint.address)

            characteristics = {
                str(char.uuid).lower()
                for service in client.services
                for char in service.characteristics
            }
            if HRS_CHAR not in characteristics:
                raise RuntimeError("0x2A37 not present; the band is not in HR Data Broadcast mode")

            def callback(_sender: object, data: bytearray) -> None:
                self._handle_packet(bytes(data))

            await client.start_notify(HRS_CHAR, callback)
            self._last_packet_monotonic = time.monotonic()
            reason = "disconnected"
            while not self._stop.is_set():
                control = self._control()
                if control.paused:
                    reason = "paused"
                    break
                if control.force_reconnect != self._last_force_seen:
                    self._last_force_seen = control.force_reconnect
                    reason = "reconnect_requested"
                    break
                if disconnected.is_set() or not client.is_connected:
                    reason = "disconnected"
                    break
                if (
                    self._last_packet_monotonic is not None
                    and time.monotonic() - self._last_packet_monotonic > self.config.stale_timeout
                ):
                    reason = "stale_connection"
                    self.db.add_event(
                        "stale_connection",
                        session_id=self._session_id,
                        details={"timeout_s": self.config.stale_timeout},
                    )
                    LOG.warning("no HR packets for %.1fs; reconnecting", self.config.stale_timeout)
                    break
                try:
                    await asyncio.wait_for(disconnected.wait(), timeout=1.0)
                except TimeoutError:
                    continue
                reason = "disconnected"
                break
        finally:
            try:
                if client.is_connected:
                    await client.stop_notify(HRS_CHAR)
            except Exception:  # noqa: BLE001, S110 - best effort
                pass
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001, S110 - best effort
                pass
        duration = time.monotonic() - started
        return ConnectionResult(
            reason=reason, duration=duration, packets=self._session_packets - start_packets
        )

    async def _find_endpoint(self):
        try:
            endpoint = await find_endpoint(
                endpoint="hr_broadcast",
                timeout=self.config.scan_timeout,
                address=self.config.address,
            )
        except BleakError as exc:
            self.state.update(adapter_available=False, last_error=f"adapter: {exc}")
            if time.time() - self._last_scan_event > 300:
                self._last_scan_event = time.time()
                self.db.add_event(
                    "adapter_unavailable",
                    session_id=self._session_id,
                    details={"error": str(exc)},
                )
            LOG.warning("BLE scan failed: %s", exc)
            return None
        if endpoint is None:
            self.state.update(adapter_available=True)
            if time.time() - self._last_scan_event > 120:
                self._last_scan_event = time.time()
                self.db.add_event(
                    "scan_miss",
                    session_id=self._session_id,
                    details={"message": "HR broadcast endpoint not advertising"},
                )
        return endpoint

    # --- lifecycle ---------------------------------------------------------
    async def run(self) -> None:
        config = self.config
        self._last_force_seen = self._control().force_reconnect
        self._session_started = time.time()
        self._session_id = self.db.start_session(
            device_id=self.state.snapshot().get("device_id") or "unknown",
            expected_sampling_interval=config.expected_interval,
            metadata={"mode": "ble_hrs"},
        )
        self.db.add_event("monitoring_started", session_id=self._session_id)
        self.state.update(
            force=True,
            service_status="running",
            connection_status="starting",
            session_id=self._session_id,
            session_started_at=time.time(),
            expected_sampling_interval_s=config.expected_interval,
            started_at=time.time(),
            paused=False,
        )
        LOG.info("monitoring session %s started", self._session_id)

        try:
            while not self._stop.is_set():
                control = self._control()
                if control.paused:
                    self.state.update(connection_status="paused", paused=True, force=True)
                    if not self._paused_event_logged:
                        self.db.add_event("monitoring_paused", session_id=self._session_id)
                        self._paused_event_logged = True
                    await self._sleep(1.0)
                    continue
                if self._paused_event_logged:
                    self.db.add_event("monitoring_resumed", session_id=self._session_id)
                    self._paused_event_logged = False
                self.state.update(paused=False, force=True)
                self.db.set_session_status(self._session_id, "active")
                self._drain_spool_if_due()
                self._failures += 1
                self._attempts += 1
                self.state.update(
                    reconnect_attempts=self._attempts,
                    consecutive_failures=self._failures,
                    connection_status="scanning",
                    force=True,
                )
                try:
                    result = await self._connect_and_stream()
                except Exception as exc:
                    self.db.add_event(
                        "error",
                        session_id=self._session_id,
                        details={"error": f"{type(exc).__name__}: {exc}"},
                    )
                    self.state.update(last_error=f"{type(exc).__name__}: {exc}")
                    LOG.exception("connection attempt failed")
                    result = None

                if self._stop.is_set():
                    break

                now = time.time()
                self.state.update(
                    last_disconnection_at=now,
                    connection_status="disconnected",
                    force=True,
                )
                if result is not None:
                    if result.reason not in ("paused", "reconnect_requested"):
                        self._disconnects += 1
                    self.db.set_session_status(self._session_id, "disconnected")
                    self.db.add_event(
                        "disconnected",
                        session_id=self._session_id,
                        details={
                            "reason": result.reason,
                            "duration_s": round(result.duration, 3),
                            "packets": result.packets,
                        },
                    )
                    self.db.update_session_stats(
                        self._session_id,
                        actual_sampling_interval=self._sample_interval(),
                        disconnect_count=self._disconnects,
                    )
                    LOG.info(
                        "connection ended: reason=%s duration=%.1fs packets=%d",
                        result.reason,
                        result.duration,
                        result.packets,
                    )
                    if result.duration >= config.stable_after:
                        self._failures = 0
                        self.state.update(consecutive_failures=0)
                if self._stop.is_set():
                    break
                if self._last_control.paused:
                    continue
                delay = self._backoff_seconds()
                self.state.update(next_retry_at=time.time() + delay, force=True)
                LOG.info("reconnecting in %.1fs", delay)
                if not await self._sleep(delay):
                    break
        finally:
            self.db.end_session(
                self._session_id,
                status="stopped",
                actual_sampling_interval=self._sample_interval(),
            )
            self.db.add_event("monitoring_stopped", session_id=self._session_id)
            self.state.update(
                force=True,
                service_status="stopped",
                connection_status="stopped",
                paused=False,
            )
            LOG.info("monitoring session %s stopped", self._session_id)

    def _drain_spool_if_due(self) -> None:
        if time.time() - self._last_spool_drain < self.config.spool_drain_interval:
            return
        self._last_spool_drain = time.time()
        drained = self.spool.drain(lambda row: self.db.add_measurement(**row))
        if drained:
            LOG.info("drained %d spooled observations", drained)
            self.db.add_event(
                "spool_drained", session_id=self._session_id, details={"count": drained}
            )

    async def _sleep(self, seconds: float) -> bool:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
            return False
        except TimeoutError:
            return True


__all__ = ["HRS_CHAR", "HRS_SERVICE", "BandHRCollector", "CollectorConfig", "ConnectionResult"]
