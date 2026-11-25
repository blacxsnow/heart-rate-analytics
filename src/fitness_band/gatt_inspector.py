"""Read-only GATT enumeration and notification capture.

Safety policy
-------------
* Enumerating services/characteristics/descriptors is read-only.
* Reads are restricted to an allow-list of standard, side-effect-free
  characteristics. Unknown vendor characteristics are never read by default.
* Notifications are enabled only for characteristics explicitly requested (or
  the standard Heart Rate Measurement by default). Enabling notifications writes
  only the standard CCCD descriptor; no vendor command is sent.
* No arbitrary writes are issued by this module.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bleak import BleakClient

from . import uuids

SAFE_READ_UUIDS = {
    uuids.DEVICE_NAME,
    uuids.APPEARANCE,
    uuids.PERIPHERAL_PREFERRED_CONNECTION_PARAMETERS,
    uuids.MANUFACTURER_NAME,
    uuids.MODEL_NUMBER,
    uuids.SERIAL_NUMBER,
    uuids.FIRMWARE_REVISION,
    uuids.HARDWARE_REVISION,
    uuids.SOFTWARE_REVISION,
    uuids.BATTERY_LEVEL,
    uuids.BODY_SENSOR_LOCATION,
}

DEFAULT_NOTIFY_UUIDS = {uuids.HEART_RATE_MEASUREMENT}

CHARACTERISTIC_NAMES = {
    uuids.DEVICE_NAME: "Device Name",
    uuids.APPEARANCE: "Appearance",
    uuids.MANUFACTURER_NAME: "Manufacturer Name",
    uuids.MODEL_NUMBER: "Model Number",
    uuids.SERIAL_NUMBER: "Serial Number",
    uuids.FIRMWARE_REVISION: "Firmware Revision",
    uuids.HARDWARE_REVISION: "Hardware Revision",
    uuids.SOFTWARE_REVISION: "Software Revision",
    uuids.HEART_RATE_MEASUREMENT: "Heart Rate Measurement",
    uuids.BODY_SENSOR_LOCATION: "Body Sensor Location",
    uuids.HEART_RATE_CONTROL_POINT: "Heart Rate Control Point",
    uuids.BATTERY_LEVEL: "Battery Level",
    uuids.HUAWEI_WRITE: "Huawei Link write (FE01)",
    uuids.HUAWEI_READ: "Huawei Link notify (FE02)",
}


def _text(value: bytes) -> str | None:
    try:
        decoded = value.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return decoded if decoded.isprintable() else None


@dataclass
class Notification:
    ts: float
    iso: str
    characteristic: str
    data_hex: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "iso": self.iso,
            "characteristic": self.characteristic,
            "data_hex": self.data_hex,
        }


@dataclass
class GattReport:
    address: str
    name: str | None
    connected_at: float
    mtu: int | None
    services: list[dict[str, Any]] = field(default_factory=list)
    reads: dict[str, dict[str, Any]] = field(default_factory=dict)
    notifications: list[Notification] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    disconnected_at: float | None = None

    @property
    def heart_rate_service_present(self) -> bool:
        return any(s["uuid"].lower() == uuids.HEART_RATE_SERVICE for s in self.services)

    @property
    def huawei_service_present(self) -> bool:
        return any(s["uuid"].lower() == uuids.HUAWEI_SERVICE for s in self.services)

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "name": self.name,
            "connected_at": self.connected_at,
            "connected_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(self.connected_at)),
            "disconnected_at": self.disconnected_at,
            "mtu": self.mtu,
            "heart_rate_service_present": self.heart_rate_service_present,
            "huawei_service_present": self.huawei_service_present,
            "services": self.services,
            "reads": self.reads,
            "notifications": [n.to_dict() for n in self.notifications],
            "errors": self.errors,
        }


async def inspect_gatt(
    address: str,
    *,
    read_safe: bool = True,
    subscribe_seconds: float = 0.0,
    notify_uuids: set[str] | None = None,
    subscribe_all_notify: bool = False,
    timeout: float = 30.0,
    on_notification: Callable[[Notification], None] | None = None,
) -> GattReport:
    """Connect, enumerate GATT, optionally read safe values and subscribe."""
    report = GattReport(address=address, name=None, connected_at=time.time(), mtu=None)
    notify_uuids = {u.lower() for u in (notify_uuids or DEFAULT_NOTIFY_UUIDS)}

    async with BleakClient(address, timeout=timeout) as client:
        report.name = getattr(client, "name", None)
        report.mtu = getattr(client, "mtu_size", None) or getattr(client, "mtu", None)
        for service in client.services:
            service_entry = {
                "uuid": str(service.uuid).lower(),
                "description": service.description,
                "known_name": uuids.SERVICE_NAMES.get(str(service.uuid).lower()),
                "characteristics": [],
            }
            for char in service.characteristics:
                char_entry = {
                    "uuid": str(char.uuid).lower(),
                    "description": char.description,
                    "known_name": CHARACTERISTIC_NAMES.get(str(char.uuid).lower()),
                    "handle": char.handle,
                    "properties": list(char.properties),
                    "descriptors": [
                        {
                            "uuid": str(desc.uuid).lower(),
                            "handle": desc.handle,
                            "description": desc.description,
                        }
                        for desc in char.descriptors
                    ],
                }
                service_entry["characteristics"].append(char_entry)
            report.services.append(service_entry)

        if read_safe:
            for service in report.services:
                for char in service["characteristics"]:
                    uuid = char["uuid"]
                    if uuid not in SAFE_READ_UUIDS or "read" not in char["properties"]:
                        continue
                    entry: dict[str, Any] = {"uuid": uuid, "name": CHARACTERISTIC_NAMES.get(uuid)}
                    try:
                        value = await asyncio.wait_for(
                            client.read_gatt_char(uuid),
                            timeout=min(8.0, timeout),
                        )
                        entry.update(
                            {
                                "ok": True,
                                "value_hex": value.hex(),
                                "value_text": _text(value),
                                "length": len(value),
                            }
                        )
                    except Exception as exc:  # noqa: BLE001 - report every failure
                        entry.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
                    report.reads[uuid] = entry

        wanted: list[str] = []
        for service in report.services:
            for char in service["characteristics"]:
                if "notify" not in char["properties"] and "indicate" not in char["properties"]:
                    continue
                uuid = char["uuid"]
                if subscribe_all_notify or uuid in notify_uuids:
                    wanted.append(uuid)

        def make_callback(char_uuid: str) -> Callable[[Any, bytearray], None]:
            def callback(_sender: Any, data: bytearray) -> None:
                notification = Notification(
                    ts=time.time(),
                    iso=time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
                    characteristic=char_uuid,
                    data_hex=bytes(data).hex(),
                )
                report.notifications.append(notification)
                if on_notification:
                    on_notification(notification)

            return callback

        subscribed: list[str] = []
        for uuid in wanted:
            try:
                await client.start_notify(uuid, make_callback(uuid))
                subscribed.append(uuid)
            except Exception as exc:  # noqa: BLE001
                report.errors.append(f"subscribe {uuid}: {type(exc).__name__}: {exc}")

        if subscribed and subscribe_seconds > 0:
            await asyncio.sleep(subscribe_seconds)
            for uuid in subscribed:
                try:
                    await client.stop_notify(uuid)
                except Exception:  # noqa: BLE001, S110 - best effort on teardown
                    pass

    report.disconnected_at = time.time()
    return report


def write_report(report: GattReport, directory: str | Path) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    slug = report.address.replace(":", "").lower()
    path = directory / f"gatt_{slug}.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path


def format_summary(report: GattReport) -> str:
    lines = [
        f"Device: {report.name or '<unknown>'}  {report.address}",
        f"MTU: {report.mtu}",
        f"HR service (0x180D): {'yes' if report.heart_rate_service_present else 'no'}",
        f"Huawei FE86 service: {'yes' if report.huawei_service_present else 'no'}",
        "",
    ]
    for service in report.services:
        lines.append(f"[{service['uuid']}] {service['known_name'] or service['description']}")
        for char in service["characteristics"]:
            lines.append(
                f"  {char['uuid']}  {','.join(char['properties'])}"
                f"  {char['known_name'] or ''}"
            )
            for desc in char["descriptors"]:
                lines.append(f"      desc {desc['uuid']} handle={desc['handle']}")
    return "\n".join(lines)
