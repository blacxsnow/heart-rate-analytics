"""Authentication reconnaissance and (future) HiChain implementation.

Current status
--------------
The Band 9 exposes a standard HRS endpoint that needs no authentication, so
the minimum viable acquisition path does not use this module.

The proprietary FE86 channel does require authentication. This module performs
only the *first* step of the documented Huawei handshake: an unencrypted
LinkParams request that reports protocol version, MTU, slice size, auth version,
device support type and bond state. It does not send a PIN, does not bond, and
does not modify the device.

Do not treat the proprietary channel as working until a full auth sequence has
been verified against the physical device.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from bleak import BleakClient

from . import uuids
from .protocol import Frame, FrameDecoder, LinkParams, build_link_params_request


@dataclass
class LinkParamsProbe:
    address: str
    started_at: float
    request_hex: str
    response_frames: list[str] = field(default_factory=list)
    link_params: LinkParams | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "address": self.address,
            "started_at": self.started_at,
            "started_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(self.started_at)),
            "request_hex": self.request_hex,
            "response_frames": self.response_frames,
            "link_params": self.link_params.to_dict() if self.link_params else None,
            "error": self.error,
            "confidence": "CONFIRMED request format; response fields LIKELY until verified",
        }


async def probe_link_params(
    address: str,
    *,
    timeout: float = 10.0,
    connect_timeout: float = 30.0,
    out_path: str | Path | None = None,
) -> LinkParamsProbe:
    """Send the read-only LinkParams handshake and decode the response.

    This is the only write this project performs during reconnaissance. It is a
    documented protocol handshake (not an arbitrary command) and changes no
    configuration. It can trigger a normal connection on the band's screen.
    """
    probe = LinkParamsProbe(
        address=address,
        started_at=time.time(),
        request_hex=build_link_params_request().hex(),
    )
    decoder = FrameDecoder()
    frames: list[Frame] = []
    got_response = asyncio.Event()

    def on_notify(_sender: object, data: bytearray) -> None:
        try:
            for frame in decoder.feed(bytes(data)):
                frames.append(frame)
                if frame.service_id == 0x01 and frame.command_id == 0x01:
                    got_response.set()
        except Exception as exc:  # noqa: BLE001 - keep raw evidence
            probe.error = f"decode: {type(exc).__name__}: {exc}"

    try:
        async with BleakClient(address, timeout=connect_timeout) as client:
            await client.start_notify(uuids.HUAWEI_READ, on_notify)
            await client.write_gatt_char(
                uuids.HUAWEI_WRITE,
                build_link_params_request(),
                response=True,
            )
            try:
                await asyncio.wait_for(got_response.wait(), timeout=timeout)
            except TimeoutError:
                probe.error = (
                    "No LinkParams response. The proprietary channel may be disabled "
                    "while HR Data Broadcast is active, or the device requires a "
                    "different endpoint."
                )
            if frames:
                probe.response_frames = [frame.raw.hex() for frame in frames]
            response = next(
                (f for f in frames if f.service_id == 0x01 and f.command_id == 0x01),
                None,
            )
            if response is not None:
                probe.link_params = LinkParams.from_tlvs(response.tlvs)
            await client.stop_notify(uuids.HUAWEI_READ)
    except Exception as exc:  # noqa: BLE001
        probe.error = f"{type(exc).__name__}: {exc}"

    if out_path:
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(probe.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return probe
