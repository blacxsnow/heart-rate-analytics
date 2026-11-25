"""Advertisement classification and endpoint-discovery tests (no hardware)."""

from __future__ import annotations

import asyncio
from typing import ClassVar

from fitness_band import ble_scanner, uuids


class FakeDevice:
    def __init__(self, address: str, name: str | None = None) -> None:
        self.address = address
        self.name = name


class FakeAdvertisement:
    def __init__(
        self,
        *,
        local_name: str | None = None,
        service_uuids: list[str] | None = None,
        rssi: int = -60,
    ) -> None:
        self.local_name = local_name
        self.service_uuids = service_uuids or []
        self.rssi = rssi
        self.manufacturer_data = {}
        self.service_data = {}
        self.tx_power = None
        self.connectable = True


class FakeScanner:
    script: ClassVar[list[tuple[FakeDevice, FakeAdvertisement]]] = []
    instances: ClassVar[list[FakeScanner]] = []

    def __init__(self, detection_callback=None) -> None:
        self.callback = detection_callback
        self.started = False
        FakeScanner.instances.append(self)

    async def start(self) -> None:
        self.started = True
        for device, advertisement in FakeScanner.script:
            self.callback(device, advertisement)

    async def stop(self) -> None:
        self.started = False


def test_normal_endpoint_name_variants() -> None:
    assert uuids.is_huawei_band9_name("HUAWEI Band 9-ABC")
    assert uuids.is_huawei_band9_name("HUAWEI Band 10-TEST")
    assert uuids.is_huawei_band9_name("HUAWEI Band 8-XYZ")
    assert not uuids.is_huawei_band9_name("HUAWEI Band HR-TEST")
    assert not uuids.is_huawei_band9_name("Fridge")
    assert not uuids.is_huawei_band9_name(None)


def test_live_normal_endpoint_is_classified() -> None:
    record = ble_scanner.Advertisement(
        address="24:AA:BB:CC:DD:EE",
        name="HUAWEI Band 10-TEST",
        rssi=-78,
        service_uuids=["00003802-0000-1000-8000-00805f9b34fb"],
    )
    assert record.is_normal_endpoint
    assert not record.is_hr_broadcast
    assert record.endpoint == "normal"


def test_find_endpoints_returns_hr_and_stops(monkeypatch) -> None:
    FakeScanner.script = [
        (
            FakeDevice("AA:BB", "HUAWEI Band HR-TEST"),
            FakeAdvertisement(
                local_name="HUAWEI Band HR-TEST",
                service_uuids=[uuids.HEART_RATE_SERVICE],
            ),
        )
    ]
    FakeScanner.instances = []
    monkeypatch.setattr(ble_scanner, "BleakScanner", FakeScanner)

    hr, normal = asyncio.run(ble_scanner.find_endpoints(timeout=0.5))
    assert hr is not None and hr.address == "AA:BB"
    assert normal is None
    assert FakeScanner.instances[-1].started is False


def test_find_endpoints_returns_normal_when_hr_absent(monkeypatch) -> None:
    FakeScanner.script = [
        (
            FakeDevice("24:AA", "HUAWEI Band 10-TEST"),
            FakeAdvertisement(
                local_name="HUAWEI Band 10-TEST",
                service_uuids=["00003802-0000-1000-8000-00805f9b34fb"],
            ),
        )
    ]
    FakeScanner.instances = []
    monkeypatch.setattr(ble_scanner, "BleakScanner", FakeScanner)

    hr, normal = asyncio.run(ble_scanner.find_endpoints(timeout=0.05))
    assert hr is None
    assert normal is not None and normal.address == "24:AA"
    assert FakeScanner.instances[-1].started is False


def test_find_endpoints_respects_address_filter(monkeypatch) -> None:
    FakeScanner.script = [
        (
            FakeDevice("AA:BB", "HUAWEI Band HR-ONE"),
            FakeAdvertisement(
                local_name="HUAWEI Band HR-ONE",
                service_uuids=[uuids.HEART_RATE_SERVICE],
            ),
        ),
        (
            FakeDevice("CC:DD", "HUAWEI Band HR-TWO"),
            FakeAdvertisement(
                local_name="HUAWEI Band HR-TWO",
                service_uuids=[uuids.HEART_RATE_SERVICE],
            ),
        ),
    ]
    FakeScanner.instances = []
    monkeypatch.setattr(ble_scanner, "BleakScanner", FakeScanner)

    hr, normal = asyncio.run(
        ble_scanner.find_endpoints(timeout=0.5, address="CC:DD")
    )
    assert hr is not None and hr.address == "CC:DD"
    assert normal is None
