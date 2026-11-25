"""Reconnect/state-machine tests for the collector using a fake BLE backend.

No Bluetooth adapter is touched. The fake endpoint and client reproduce the
behaviour that matters: advertisements appearing/disappearing, link drops,
notifications, stale links, connection errors, and dashboard control actions.
"""

from __future__ import annotations

import asyncio
import time
from typing import ClassVar

from bleak.exc import BleakDeviceNotFoundError

from fitness_band.acquisition import collector as collector_module
from fitness_band.acquisition.collector import BandHRCollector, CollectorConfig
from fitness_band.acquisition.control import apply_action
from fitness_band.acquisition.spool import SpoolQueue
from fitness_band.acquisition.state import StateWriter
from fitness_band.database import AcquisitionDB

ADDRESS = "AA:BB:CC:DD:EE:FF"
NAME = "HUAWEI Band HR-TEST"


class FakeCharacteristic:
    uuid = collector_module.HRS_CHAR


class FakeService:
    characteristics: ClassVar[list[FakeCharacteristic]] = [FakeCharacteristic()]


class FakeAdvertisement:
    address = ADDRESS
    name = NAME


class FakeNormalAdvertisement:
    """The normal (non-HRS) Band 9 endpoint, seen when broadcast is off."""

    address = "11:22:33:44:55:66"
    name = "HUAWEI Band 10-TEST"


class FakeClient:
    """A BleakClient stand-in that can stream, drop, or fail to connect."""

    def __init__(self, ble: FakeBLE, index: int, **kwargs: object) -> None:
        self.ble = ble
        self.index = index
        self.is_connected = False
        self.services = [FakeService()]
        self.disconnected_callback = kwargs.get("disconnected_callback")
        self._pump_task: asyncio.Task | None = None
        self.connected_at: float | None = None

    async def connect(self) -> None:
        error = self.ble.connect_errors.get(self.index)
        if error is not None:
            raise error
        self.is_connected = True
        self.connected_at = time.monotonic()

    async def start_notify(self, uuid: str, callback) -> None:
        assert uuid.lower() == collector_module.HRS_CHAR
        if self.index in self.ble.silent_connections:
            return
        self._pump_task = asyncio.create_task(self._pump(callback))

    async def _pump(self, callback) -> None:
        limit = self.ble.packet_plans.get(self.index)
        sent = 0
        while self.is_connected:
            await asyncio.sleep(self.ble.packet_interval)
            if not self.is_connected:
                return
            sent += 1
            callback(None, bytearray([0x06, 70 + (sent % 10), 0x00]))
            if limit is not None and sent >= limit:
                self.drop()
                return

    def drop(self) -> None:
        if not self.is_connected:
            return
        self.is_connected = False
        if callable(self.disconnected_callback):
            self.disconnected_callback(self)
        if self._pump_task is not None:
            self._pump_task.cancel()

    async def stop_notify(self, _uuid: str) -> None:
        if self._pump_task is not None:
            self._pump_task.cancel()

    async def disconnect(self) -> None:
        self.drop()


class FakeBLE:
    def __init__(self, monkeypatch) -> None:
        self.endpoint_present = True
        self.normal_visible = False
        self.scan_times: list[float] = []
        self.clients: list[FakeClient] = []
        self.packet_plans: dict[int, int | None] = {}
        self.connect_errors: dict[int, Exception] = {}
        self.silent_connections: set[int] = set()
        self.packet_interval = 0.01
        # BlueZ cache/link simulation; never touch the real adapter in tests.
        self.cached_hr = False
        self.stale_links: set[str] = set()
        self.bluez_disconnects: list[str] = []
        self.adapter_present = True
        self.adapter_powered = True
        self.adapter_discovering = False
        self.discovery_stuck = False
        self.reset_calls: list[str] = []
        monkeypatch.setattr(collector_module, "find_endpoints", self._find_endpoints)
        monkeypatch.setattr(collector_module, "BleakClient", self._make_client)
        monkeypatch.setattr(collector_module, "_bluez_devices", self._bluez_devices)
        monkeypatch.setattr(collector_module, "_bluez_connected", self._bluez_connected)
        monkeypatch.setattr(collector_module, "_bluez_show", self._bluez_show)
        monkeypatch.setattr(
            collector_module, "_stop_bluez_discovery", self._stop_bluez_discovery
        )
        monkeypatch.setattr(
            collector_module, "_reset_bluez_adapter", self._reset_bluez_adapter
        )
        monkeypatch.setattr(
            collector_module, "_disconnect_bluez_device", self._disconnect_bluez_device
        )
        monkeypatch.setattr(collector_module, "_remove_bluez_cache", lambda _address: None)

    def _bluez_devices(self, *, connected_only: bool = False) -> list[tuple[str, str]]:
        if not self.cached_hr:
            return []
        if connected_only and ADDRESS not in self.stale_links:
            return []
        return [(ADDRESS, NAME)]

    def _bluez_show(self) -> dict[str, str]:
        if not self.adapter_present:
            return {}
        return {
            "powered": "yes" if self.adapter_powered else "no",
            "discovering": "yes" if self.adapter_discovering else "no",
        }

    def _stop_bluez_discovery(self) -> bool:
        if self.discovery_stuck:
            return False
        self.adapter_discovering = False
        return True

    def _reset_bluez_adapter(self) -> tuple[bool, str]:
        self.reset_calls.append("reset")
        self.adapter_present = True
        self.adapter_powered = True
        self.adapter_discovering = False
        self.discovery_stuck = False
        return True, "fake reset"

    def _bluez_connected(self, address: str) -> bool:
        return address in self.stale_links

    def _disconnect_bluez_device(self, address: str) -> bool:
        if address not in self.stale_links:
            return False
        self.stale_links.discard(address)
        self.bluez_disconnects.append(address)
        return True

    async def _find_endpoints(self, **_kwargs):
        self.scan_times.append(time.monotonic())
        hr = FakeAdvertisement() if self.endpoint_present else None
        normal = FakeNormalAdvertisement() if (self.normal_visible and hr is None) else None
        return hr, normal

    def _make_client(self, _address: str, **kwargs) -> FakeClient:
        client = FakeClient(self, len(self.clients), **kwargs)
        self.clients.append(client)
        return client


def fast_config(**overrides) -> CollectorConfig:
    values = {
        "scan_timeout": 0.01,
        "connect_timeout": 1.0,
        "stale_timeout": 5.0,
        "expected_interval": 0.1,
        "backoff_initial": 0.01,
        "backoff_max": 0.02,
        "stable_after": 0.2,
        "spool_drain_interval": 60.0,
        "poll_interval": 0.02,
    }
    values.update(overrides)
    return CollectorConfig(**values)


def make_runtime(tmp_path, config: CollectorConfig):
    db = AcquisitionDB(tmp_path / "acq.sqlite3")
    state = StateWriter(tmp_path / "state.json", min_interval=0.0)
    spool = SpoolQueue(tmp_path / "spool")
    control_path = tmp_path / "control.json"
    collector = BandHRCollector(
        db=db,
        state=state,
        spool=spool,
        control_path=control_path,
        config=config,
    )
    return db, state, collector, control_path


async def wait_until(predicate, *, timeout: float = 5.0, label: str = "condition") -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"timed out waiting for {label}")


async def stop_collector(collector: BandHRCollector, task: asyncio.Task) -> None:
    collector.stop()
    await asyncio.wait_for(task, timeout=5.0)


def event_types(db: AcquisitionDB) -> list[str]:
    return [event["event_type"] for event in db.events(limit=1000)]


def disconnect_reasons(db: AcquisitionDB) -> list[str]:
    import json

    reasons = []
    for event in db.events(limit=1000, event_types=["disconnected"]):
        reasons.append(json.loads(event["details"] or "{}").get("reason"))
    return reasons


def test_link_drop_reconnects_and_keeps_streaming(tmp_path, monkeypatch) -> None:
    fake = FakeBLE(monkeypatch)
    fake.packet_plans = {0: 3, 1: None}

    async def scenario() -> None:
        db, state, collector, _control = make_runtime(tmp_path, fast_config())
        task = asyncio.create_task(collector.run())
        try:
            await wait_until(
                lambda: len(fake.clients) >= 2 and state.snapshot()["connection_status"] == "connected",
                label="second connection",
            )
            await wait_until(
                lambda: len(db.recent_measurements(minutes=10_000_000)) >= 4,
                label="measurements after reconnect",
            )
            assert fake.clients[0].is_connected is False
            assert db.sessions(limit=1)[0]["connection_status"] == "connected"
            assert "connected" in event_types(db)
            await wait_until(
                lambda: "disconnected" in event_types(db), label="disconnect event"
            )
            assert disconnect_reasons(db) == ["disconnected"]
            import json

            details = [
                json.loads(event["details"])
                for event in db.events(event_types=["disconnected"])
            ]
            assert details[0]["seconds_since_last_packet"] is not None
        finally:
            await stop_collector(collector, task)
            assert db.sessions(limit=1)[0]["connection_status"] == "stopped"
            db.close()

    asyncio.run(scenario())


def test_manual_reconnect_while_connected_cycles_once(tmp_path, monkeypatch) -> None:
    fake = FakeBLE(monkeypatch)

    async def scenario() -> None:
        db, state, collector, control = make_runtime(tmp_path, fast_config())
        task = asyncio.create_task(collector.run())
        try:
            await wait_until(lambda: len(fake.clients) >= 1 and state.snapshot()["current_hr"] is not None)
            apply_action(control, "reconnect")
            await wait_until(
                lambda: len(fake.clients) >= 2 and state.snapshot()["connection_status"] == "connected",
                label="reconnect after request",
            )
            assert "reconnect_requested" in disconnect_reasons(db)
            assert fake.clients[0].is_connected is False
            assert db.sessions(limit=1)[0]["connection_status"] == "connected"
        finally:
            await stop_collector(collector, task)
            db.close()

    asyncio.run(scenario())


def test_manual_reconnect_cancels_long_backoff(tmp_path, monkeypatch) -> None:
    fake = FakeBLE(monkeypatch)
    fake.endpoint_present = False

    async def scenario() -> None:
        db, state, collector, control = make_runtime(
            tmp_path, fast_config(backoff_initial=30.0, backoff_max=30.0)
        )
        task = asyncio.create_task(collector.run())
        try:
            await wait_until(
                lambda: len(fake.scan_times) >= 1 and state.snapshot()["next_retry_at"] is not None,
                label="first failed scan and pending backoff",
            )
            assert state.snapshot()["consecutive_failures"] >= 1
            fake.endpoint_present = True
            started = time.monotonic()
            apply_action(control, "reconnect")
            await wait_until(
                lambda: len(fake.clients) >= 1 and state.snapshot()["connection_status"] == "connected",
                timeout=2.0,
                label="immediate connection",
            )
            assert time.monotonic() - started < 2.0
            assert state.snapshot()["consecutive_failures"] == 0
        finally:
            await stop_collector(collector, task)
            db.close()

    asyncio.run(scenario())


def test_pause_releases_link_and_resume_reconnects(tmp_path, monkeypatch) -> None:
    fake = FakeBLE(monkeypatch)

    async def scenario() -> None:
        db, state, collector, control = make_runtime(tmp_path, fast_config())
        task = asyncio.create_task(collector.run())
        try:
            await wait_until(lambda: len(fake.clients) >= 1 and state.snapshot()["connection_status"] == "connected")
            apply_action(control, "disconnect")
            await wait_until(lambda: state.snapshot()["paused"] is True, label="paused state")
            await wait_until(lambda: fake.clients[0].is_connected is False, label="released link")
            await asyncio.sleep(0.2)
            assert len(fake.clients) == 1
            assert db.sessions(limit=1)[0]["connection_status"] == "paused"
            assert "monitoring_paused" in event_types(db)

            apply_action(control, "start")
            await wait_until(
                lambda: len(fake.clients) >= 2 and state.snapshot()["connection_status"] == "connected",
                label="resume connection",
            )
            assert state.snapshot()["paused"] is False
            assert state.snapshot()["consecutive_failures"] == 0
            assert "monitoring_resumed" in event_types(db)
            assert db.sessions(limit=1)[0]["connection_status"] == "connected"
        finally:
            await stop_collector(collector, task)
            db.close()

    asyncio.run(scenario())


def test_stale_link_triggers_watchdog_reconnect(tmp_path, monkeypatch) -> None:
    fake = FakeBLE(monkeypatch)
    fake.silent_connections = {0}

    async def scenario() -> None:
        db, state, collector, _control = make_runtime(
            tmp_path, fast_config(stale_timeout=0.2)
        )
        task = asyncio.create_task(collector.run())
        try:
            await wait_until(
                lambda: len(fake.clients) >= 2 and state.snapshot()["connection_status"] == "connected",
                label="watchdog reconnect",
            )
            assert "stale_connection" in event_types(db)
            assert "stale_connection" in disconnect_reasons(db)
        finally:
            await stop_collector(collector, task)
            db.close()

    asyncio.run(scenario())


def test_missing_endpoint_records_scan_miss_and_backs_off(tmp_path, monkeypatch) -> None:
    fake = FakeBLE(monkeypatch)
    fake.endpoint_present = False

    async def scenario() -> None:
        db, state, collector, _control = make_runtime(
            tmp_path, fast_config(backoff_initial=0.2, backoff_max=0.2)
        )
        task = asyncio.create_task(collector.run())
        try:
            await wait_until(
                lambda: state.snapshot()["consecutive_failures"] >= 2,
                label="repeated scan failures",
            )
            await wait_until(
                lambda: state.snapshot()["next_retry_at"] is not None,
                label="backoff state",
            )
            await wait_until(
                lambda: "scan_miss" in event_types(db), label="scan_miss event"
            )
            await wait_until(
                lambda: "error" in event_types(db), label="error event"
            )
            snapshot = state.snapshot()
            assert snapshot["connection_status"] == "disconnected"
            assert "HR broadcast endpoint not found" in (snapshot["last_error"] or "")
            assert len(fake.scan_times) >= 2
        finally:
            await stop_collector(collector, task)
            db.close()

    asyncio.run(scenario())


def test_connect_not_found_removes_stale_bluez_cache(tmp_path, monkeypatch) -> None:
    fake = FakeBLE(monkeypatch)
    fake.connect_errors = {0: BleakDeviceNotFoundError(ADDRESS, "not found")}
    removed: list[str] = []
    monkeypatch.setattr(collector_module, "_remove_bluez_cache", removed.append)

    async def scenario() -> None:
        db, state, collector, _control = make_runtime(tmp_path, fast_config())
        task = asyncio.create_task(collector.run())
        try:
            await wait_until(
                lambda: len(fake.clients) >= 2 and state.snapshot()["connection_status"] == "connected",
                label="connection after cache cleanup",
            )
            assert removed == [ADDRESS]
            types = event_types(db)
            assert "connect_failed" in types
            assert "bluez_cache_removed" in types
        finally:
            await stop_collector(collector, task)
            db.close()

    asyncio.run(scenario())


def test_stale_connected_link_is_released_before_scan(tmp_path, monkeypatch) -> None:
    """A stale BlueZ connection hides the advertisement; cleanup restores it."""
    fake = FakeBLE(monkeypatch)
    fake.cached_hr = True
    fake.stale_links = {ADDRESS}
    fake.endpoint_present = False

    original_cleanup = fake._disconnect_bluez_device

    def cleanup_and_resume(address: str) -> bool:
        released = original_cleanup(address)
        if released:
            # Disconnecting a stale link makes the band advertise again.
            fake.endpoint_present = True
        return released

    monkeypatch.setattr(
        collector_module, "_disconnect_bluez_device", cleanup_and_resume
    )

    async def scenario() -> None:
        db, state, collector, _control = make_runtime(tmp_path, fast_config())
        task = asyncio.create_task(collector.run())
        try:
            await wait_until(
                lambda: state.snapshot()["connection_status"] == "connected",
                label="connection after stale-link cleanup",
            )
            assert fake.bluez_disconnects == [ADDRESS]
            assert fake.scan_times, "scan should run after cleanup"
            assert "stale_link_cleared" in event_types(db)
            assert fake.clients[0].is_connected is True
        finally:
            await stop_collector(collector, task)
            db.close()

    asyncio.run(scenario())


def test_band_nearby_with_broadcast_off_is_reported(tmp_path, monkeypatch) -> None:
    fake = FakeBLE(monkeypatch)
    fake.endpoint_present = False
    fake.normal_visible = True

    async def scenario() -> None:
        db, state, collector, _control = make_runtime(tmp_path, fast_config())
        task = asyncio.create_task(collector.run())
        try:
            await wait_until(
                lambda: state.snapshot()["hr_broadcast_active"] is False,
                label="broadcast-off classification",
            )
            snapshot = state.snapshot()
            assert snapshot["band_visible"] is True
            assert snapshot["adapter_available"] is True
            await wait_until(
                lambda: "hr_broadcast_off" in event_types(db),
                label="hr_broadcast_off event",
            )
            assert "HR Data Broadcast" in (snapshot["last_error"] or "")
            assert "HR broadcast endpoint not found" not in (snapshot["last_error"] or "")
        finally:
            await stop_collector(collector, task)
            db.close()

    asyncio.run(scenario())


def test_visible_band_uses_short_backoff(tmp_path, monkeypatch) -> None:
    fake = FakeBLE(monkeypatch)
    fake.endpoint_present = False
    fake.normal_visible = True

    async def scenario() -> None:
        config = fast_config(
            backoff_initial=30.0,
            backoff_max=30.0,
            visible_band_backoff_max=0.2,
        )
        db, state, collector, _control = make_runtime(tmp_path, config)
        task = asyncio.create_task(collector.run())
        try:
            await wait_until(
                lambda: state.snapshot()["consecutive_failures"] >= 1
                and state.snapshot()["next_retry_at"] is not None,
                label="visible-band backoff",
            )
            snapshot = state.snapshot()
            remaining = snapshot["next_retry_at"] - time.time()
            assert 0 < remaining <= 1.0, remaining
        finally:
            await stop_collector(collector, task)
            db.close()

    asyncio.run(scenario())


def test_adapter_powered_off_is_reported(tmp_path, monkeypatch) -> None:
    fake = FakeBLE(monkeypatch)
    fake.adapter_powered = False

    async def scenario() -> None:
        db, state, collector, _control = make_runtime(tmp_path, fast_config())
        task = asyncio.create_task(collector.run())
        try:
            await wait_until(
                lambda: state.snapshot()["last_failure"] == "adapter_powered_off",
                label="powered-off failure",
            )
            snapshot = state.snapshot()
            assert snapshot["adapter_powered"] is False
            assert snapshot["adapter_available"] is True
            assert fake.scan_times == []
            assert "adapter_powered_off" in event_types(db)
        finally:
            await stop_collector(collector, task)
            db.close()

    asyncio.run(scenario())


def test_adapter_unavailable_is_reported(tmp_path, monkeypatch) -> None:
    fake = FakeBLE(monkeypatch)
    fake.adapter_present = False

    async def scenario() -> None:
        db, state, collector, _control = make_runtime(tmp_path, fast_config())
        task = asyncio.create_task(collector.run())
        try:
            await wait_until(
                lambda: state.snapshot()["last_failure"] == "adapter_unavailable",
                label="adapter-unavailable failure",
            )
            snapshot = state.snapshot()
            assert snapshot["adapter_available"] is False
            assert fake.scan_times == []
            assert "adapter_unavailable" in event_types(db)
        finally:
            await stop_collector(collector, task)
            db.close()

    asyncio.run(scenario())


def test_reset_adapter_control_action(tmp_path, monkeypatch) -> None:
    fake = FakeBLE(monkeypatch)
    fake.adapter_powered = False

    async def scenario() -> None:
        config = fast_config(backoff_initial=30.0, backoff_max=30.0)
        db, state, collector, control = make_runtime(tmp_path, config)
        task = asyncio.create_task(collector.run())
        try:
            await wait_until(
                lambda: state.snapshot()["last_failure"] == "adapter_powered_off",
                label="powered-off state",
            )
            apply_action(control, "reset_adapter")
            await wait_until(lambda: bool(fake.reset_calls), label="adapter reset")
            await wait_until(
                lambda: "adapter_reset" in event_types(db),
                label="adapter_reset event",
            )
            await wait_until(
                lambda: state.snapshot()["connection_status"] == "connected",
                label="connection after reset",
            )
        finally:
            await stop_collector(collector, task)
            db.close()

    asyncio.run(scenario())


def test_stuck_discovery_triggers_adapter_reset(tmp_path, monkeypatch) -> None:
    fake = FakeBLE(monkeypatch)
    fake.adapter_discovering = True
    fake.discovery_stuck = True

    async def scenario() -> None:
        config = fast_config(adapter_reset_after=1)
        db, _state, collector, _control = make_runtime(tmp_path, config)
        task = asyncio.create_task(collector.run())
        try:
            await wait_until(
                lambda: bool(fake.reset_calls), label="automatic adapter reset"
            )
            assert "bluez_discovery_stuck" in event_types(db)
            assert "adapter_reset" in event_types(db)
        finally:
            await stop_collector(collector, task)
            db.close()

    asyncio.run(scenario())


def test_exception_classification() -> None:
    classify = collector_module._classify_exception
    assert classify(collector_module.BroadcastOffError("x")) == "hr_broadcast_off"
    assert classify(collector_module.AdapterPoweredOffError("x")) == "adapter_powered_off"
    assert classify(collector_module.AdapterUnavailableError("x")) == "adapter_unavailable"
    assert classify(TimeoutError()) == "connect_timeout"
    assert classify(RuntimeError("org.bluez.Error.InProgress")) == "connect_in_progress"
    assert classify(RuntimeError("br-connection-canceled")) == "connect_canceled"
    assert classify(RuntimeError("HR broadcast endpoint not found")) == "band_not_visible"



