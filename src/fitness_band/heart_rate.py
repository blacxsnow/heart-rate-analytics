"""Continuous heart-rate acquisition over the standard BLE Heart Rate Service.

Verified behaviour on the Huawei Band 9 (firmware reported by the device's
generic DIS is ``1.0.0.1``; real firmware requires the proprietary channel):

* endpoint name ``HUAWEI Band HR-XXX``
* service 0x180D, characteristic 0x2A37
* one notification per second, flags 0x06, uint8 BPM, skin contact detected
* no RR intervals in the notification, therefore no HRV from this path
* continues while the display is off; requires the user to start
  ``Settings -> HR Data Broadcasts`` on the band

This module reconnects on drop and stores both raw packets and decoded values.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bleak import BleakClient

from .device_manager import DeviceManager, Endpoint
from .hrs import HeartRateMeasurement, HeartRateParseError, parse_heart_rate_measurement
from .storage import SQLiteStore, iso_utc


@dataclass
class MonitorStats:
    started_at: float
    ended_at: float | None = None
    packets: int = 0
    parse_errors: int = 0
    connections: int = 0
    disconnects: int = 0
    last_heart_rate: int | None = None
    last_packet_at: float | None = None


class HeartRateMonitor:
    def __init__(
        self,
        *,
        store: SQLiteStore,
        address: str | None = None,
        scan_timeout: float = 15.0,
        connect_timeout: float = 30.0,
        reconnect: bool = True,
        jsonl_path: str | Path | None = None,
        on_measurement: Callable[[HeartRateMeasurement, float], None] | None = None,
        on_status: Callable[[str, dict], None] | None = None,
    ) -> None:
        self.store = store
        self.manager = DeviceManager(
            address=address,
            endpoint="hr_broadcast",
            scan_timeout=scan_timeout,
            connect_timeout=connect_timeout,
        )
        self.reconnect = reconnect
        self.jsonl_path = Path(jsonl_path) if jsonl_path else None
        self.on_measurement = on_measurement
        self.on_status = on_status
        self.stats = MonitorStats(started_at=time.time())
        self._stop = asyncio.Event()
        self._address: str | None = None
        self._jsonl = None
        if self.jsonl_path:
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            self._jsonl = self.jsonl_path.open("a", encoding="utf-8")

    def stop(self) -> None:
        self._stop.set()

    def _status(self, state: str, **extra: object) -> None:
        if self.on_status:
            self.on_status(state, extra)

    def _write_jsonl(self, record: dict) -> None:
        if self._jsonl:
            self._jsonl.write(json.dumps(record, sort_keys=True) + "\n")
            self._jsonl.flush()

    async def run(self, duration: float | None = None) -> MonitorStats:
        deadline = time.monotonic() + duration if duration else None
        backoff = 2.0
        try:
            while not self._stop.is_set():
                if deadline is not None and time.monotonic() >= deadline:
                    break
                endpoint = await self.manager.resolve()
                if endpoint is None:
                    self._status("scan_miss", message="HR broadcast endpoint not found")
                    if not await self._sleep_or_stop(5.0):
                        break
                    continue
                try:
                    await self._connect_and_stream(endpoint, deadline)
                    backoff = 2.0
                except Exception as exc:
                    self._status("error", error=f"{type(exc).__name__}: {exc}")
                    self.store.add_event("error", "heart-rate session failed", {"error": str(exc)})
                    if not self.reconnect:
                        raise
                    if not await self._sleep_or_stop(backoff):
                        break
                    backoff = min(backoff * 2, 30.0)
        finally:
            self.stats.ended_at = time.time()
            if self._jsonl:
                self._jsonl.close()
        return self.stats

    async def _connect_and_stream(self, endpoint: Endpoint, deadline: float | None) -> None:
        disconnected = asyncio.Event()

        def on_disconnect(_client: BleakClient) -> None:
            disconnected.set()

        self._status("connecting", address=endpoint.address, name=endpoint.name)
        client = BleakClient(
            endpoint.address,
            timeout=self.manager.connect_timeout,
            disconnected_callback=on_disconnect,
        )
        await client.connect()
        self.stats.connections += 1
        self._address = endpoint.address
        self.store.upsert_device(endpoint.address, endpoint.name)
        session_id = self.store.start_session(endpoint.address, "ble_hrs")
        self._status("connected", address=endpoint.address, session_id=session_id)

        try:
            characteristics = {
                str(char.uuid).lower()
                for service in client.services
                for char in service.characteristics
            }
            if "00002a37-0000-1000-8000-00805f9b34fb" not in characteristics:
                raise RuntimeError(
                    "0x2A37 not present. The band is not in HR Data Broadcast mode, "
                    "or you connected to the normal (proprietary) endpoint."
                )

            def callback(_sender: object, data: bytearray) -> None:
                self._handle_packet(session_id, bytes(data))

            await client.start_notify("00002a37-0000-1000-8000-00805f9b34fb", callback)
            while not self._stop.is_set() and client.is_connected:
                if deadline is not None and time.monotonic() >= deadline:
                    break
                try:
                    await asyncio.wait_for(disconnected.wait(), timeout=1.0)
                    break
                except TimeoutError:
                    continue
        finally:
            try:
                if client.is_connected:
                    await client.stop_notify("00002a37-0000-1000-8000-00805f9b34fb")
            except Exception:  # noqa: BLE001, S110 - best effort on teardown
                pass
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001, S110 - best effort on teardown
                pass
            self.stats.disconnects += 1
            self.store.end_session(session_id)
            self._status("disconnected", session_id=session_id)

    def _handle_packet(self, session_id: int, data: bytes) -> None:
        ts = time.time()
        self.stats.packets += 1
        self.stats.last_packet_at = ts
        self.store.add_raw_packet(
            direction="rx",
            characteristic="00002a37-0000-1000-8000-00805f9b34fb",
            data=data,
            session_id=session_id,
            ts=ts,
        )
        try:
            measurement = parse_heart_rate_measurement(data)
        except HeartRateParseError as exc:
            self.stats.parse_errors += 1
            self.store.add_event("warn", "heart-rate parse error", {"error": str(exc), "raw": data.hex()})
            self._write_jsonl({"kind": "parse_error", "ts": ts, "raw": data.hex(), "error": str(exc)})
            return

        self.stats.last_heart_rate = measurement.heart_rate_bpm
        self.store.add_measurement(
            metric="heart_rate",
            value=measurement.heart_rate_bpm,
            unit="bpm",
            source="ble_hrs",
            device_address=self._address,
            session_id=session_id,
            ts=ts,
            quality="good" if measurement.sensor_contact is not False else "no_contact",
            raw=data,
            meta={
                "flags": measurement.flags,
                "sensor_contact": measurement.sensor_contact,
                "rr_intervals_s": measurement.rr_intervals_s,
            },
        )
        self._write_jsonl(
            {
                "kind": "heart_rate",
                "ts": ts,
                "iso": iso_utc(ts),
                **measurement.to_dict(),
                "raw": data.hex(),
            }
        )
        if self.on_measurement:
            self.on_measurement(measurement, ts)

    async def _sleep_or_stop(self, seconds: float) -> bool:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
            return False
        except TimeoutError:
            return True
