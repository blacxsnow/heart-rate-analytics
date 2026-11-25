"""Device endpoint resolution and safe connection helpers."""

from __future__ import annotations

from dataclasses import dataclass

from bleak import BleakClient

from .ble_scanner import Advertisement, find_endpoint, scan


@dataclass
class Endpoint:
    address: str
    name: str | None
    kind: str
    rssi: int

    @classmethod
    def from_advertisement(cls, adv: Advertisement) -> Endpoint:
        return cls(address=adv.address, name=adv.name, kind=adv.endpoint, rssi=adv.rssi)


class DeviceManager:
    def __init__(
        self,
        *,
        address: str | None = None,
        endpoint: str = "hr_broadcast",
        scan_timeout: float = 15.0,
        connect_timeout: float = 30.0,
    ) -> None:
        self.address = address
        self.endpoint = endpoint
        self.scan_timeout = scan_timeout
        self.connect_timeout = connect_timeout

    async def resolve(self) -> Endpoint | None:
        if self.address:
            # Verify what is actually advertising. This avoids connecting to a
            # stale address left in BlueZ's cache after a random address change.
            results = await scan(3.0, address=self.address)
            if results:
                return Endpoint.from_advertisement(results[0])
            adv = await find_endpoint(endpoint="any", timeout=self.scan_timeout, address=self.address)
            return Endpoint.from_advertisement(adv) if adv else None
        adv = await find_endpoint(endpoint=self.endpoint, timeout=self.scan_timeout)
        return Endpoint.from_advertisement(adv) if adv else None

    async def connect(self) -> tuple[BleakClient, Endpoint]:
        endpoint = await self.resolve()
        if endpoint is None:
            raise TimeoutError(
                f"No Band 9 endpoint '{self.endpoint}' found in {self.scan_timeout:.0f}s. "
                "On the band: Settings -> HR Data Broadcasts -> start, keep screen awake."
            )
        client = BleakClient(endpoint.address, timeout=self.connect_timeout)
        await client.connect()
        return client, endpoint


async def wait_for_hr_service(address: str, timeout: float = 15.0) -> bool:
    """Return True if the endpoint currently exposes 0x180D."""
    results = await scan(min(timeout, 8.0), address=address)
    return bool(results and results[0].is_hr_broadcast)


async def disconnect_quietly(address: str) -> None:
    """Best-effort BlueZ disconnect (does not unpair or forget the device)."""
    try:
        from bleak import BleakClient

        client = BleakClient(address, timeout=10)
        if await client.connect():
            await client.disconnect()
    except Exception:  # noqa: BLE001, S110 - helper must never mask the caller's error
        pass


async def power_cycle_hint() -> str:
    return (
        "If the band is connected to a phone, turn phone Bluetooth off temporarily. "
        "The Band 9 normally accepts one active BLE link."
    )


__all__ = ["DeviceManager", "Endpoint", "disconnect_quietly", "wait_for_hr_service"]
