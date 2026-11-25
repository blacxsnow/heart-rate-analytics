"""BLE discovery for the Huawei Band 9.

Two distinct endpoints can appear:

* ``HUAWEI Band 9-XXX``  - normal proprietary endpoint (FE86), no 0x180D
* ``HUAWEI Band HR-XXX`` - HR-broadcast endpoint, advertises 0x180D

They use different addresses. Always resolve the endpoint you need by name or
service UUID; never hard-code a MAC address in committed files.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from . import uuids


@dataclass
class Advertisement:
    address: str
    name: str | None
    rssi: int
    service_uuids: list[str] = field(default_factory=list)
    manufacturer_data: dict[int, str] = field(default_factory=dict)
    service_data: dict[str, str] = field(default_factory=dict)
    tx_power: int | None = None
    connectable: bool | None = None
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    seen_count: int = 1
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_hr_broadcast(self) -> bool:
        return uuids.HEART_RATE_SERVICE in {u.lower() for u in self.service_uuids} or uuids.is_huawei_hr_broadcast_name(
            self.name
        )

    @property
    def is_normal_endpoint(self) -> bool:
        return uuids.HUAWEI_SERVICE in {u.lower() for u in self.service_uuids} or uuids.is_huawei_band9_name(
            self.name
        )

    @property
    def endpoint(self) -> str:
        if self.is_hr_broadcast:
            return "hr_broadcast"
        if self.is_normal_endpoint:
            return "normal"
        return "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "name": self.name,
            "rssi": self.rssi,
            "endpoint": self.endpoint,
            "service_uuids": self.service_uuids,
            "manufacturer_data": {str(k): v for k, v in self.manufacturer_data.items()},
            "service_data": self.service_data,
            "tx_power": self.tx_power,
            "connectable": self.connectable,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "seen_count": self.seen_count,
        }


def _from_bleak(device: BLEDevice, adv: AdvertisementData) -> Advertisement:
    return Advertisement(
        address=device.address,
        name=device.name or adv.local_name,
        rssi=adv.rssi,
        service_uuids=[str(u).lower() for u in adv.service_uuids],
        manufacturer_data={int(k): bytes(v).hex() for k, v in adv.manufacturer_data.items()},
        service_data={str(k).lower(): bytes(v).hex() for k, v in adv.service_data.items()},
        tx_power=adv.tx_power,
        connectable=getattr(adv, "connectable", None),
    )


async def scan(
    duration: float = 10.0,
    *,
    name_contains: str | None = None,
    address: str | None = None,
    service_uuid: str | None = None,
) -> list[Advertisement]:
    """Scan and merge repeated advertisements from the same address."""
    found: dict[str, Advertisement] = {}
    wanted_service = service_uuid.lower() if service_uuid else None
    wanted_name = name_contains.lower() if name_contains else None

    def callback(device: BLEDevice, adv: AdvertisementData) -> None:
        record = _from_bleak(device, adv)
        if address and record.address.upper() != address.upper():
            return
        if wanted_name and wanted_name not in (record.name or "").lower():
            return
        if wanted_service and wanted_service not in record.service_uuids:
            return
        previous = found.get(record.address)
        if previous:
            previous.rssi = record.rssi
            previous.last_seen = record.last_seen
            previous.seen_count += 1
            previous.service_uuids = sorted(set(previous.service_uuids) | set(record.service_uuids))
            previous.manufacturer_data.update(record.manufacturer_data)
            previous.service_data.update(record.service_data)
            previous.connectable = record.connectable or previous.connectable
        else:
            found[record.address] = record

    scanner = BleakScanner(detection_callback=callback)
    await scanner.start()
    try:
        await asyncio.sleep(duration)
    finally:
        await scanner.stop()

    return sorted(found.values(), key=lambda item: item.rssi, reverse=True)


async def find_endpoint(
    *,
    endpoint: str = "hr_broadcast",
    timeout: float = 15.0,
    address: str | None = None,
) -> Advertisement | None:
    """Find the HR-broadcast or normal Band 9 endpoint."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        results = await scan(
            min(5.0, max(1.0, deadline - time.monotonic())),
            address=address,
        )
        for item in results:
            if endpoint == "any":
                if item.is_hr_broadcast or item.is_normal_endpoint:
                    return item
            elif item.endpoint == endpoint:
                return item
        if address:
            # A direct address may not be advertising yet; keep trying until
            # the deadline rather than failing immediately.
            continue
    return None


async def resolve_device(address: str, timeout: float = 15.0) -> BLEDevice | None:
    """Resolve an address to a BLEDevice, preferring a fresh advertisement."""
    return await BleakScanner.find_device_by_address(address, timeout=timeout)
