"""Huawei Link Protocol framing (LPv2 family) and packet decoding.

Confidence levels used in this project
--------------------------------------
CONFIRMED  Verified against the physical Band 9 in this repository, or directly
           cross-checked against two independent open-source implementations.
LIKELY     Implemented from Gadgetbridge/Huawhoop and consistent with the
           physical device, but a specific command has not been exercised.
HYPOTHESIS Inferred; must not be treated as working.

This module currently implements:
  * CONFIRMED: CRC16-HQXQ and the unsliced frame layout (the LinkParams
    request bytes below match the format published in the 2019 Huawei Health
    reverse-engineering talk and Gadgetbridge's serializer).
  * LIKELY: TLV varint length decoding, LinkParams response field layout.
  * HYPOTHESIS: sliced-frame reassembly (needed only for large payloads).

Nothing in this module writes to the device.
"""

from __future__ import annotations

import binascii
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

MAGIC = 0x5A
HEADER_SIZE = 4  # magic + 2-byte length + slice byte
CRC_SIZE = 2

# Service IDs (Gadgetbridge devices/huawei/packets/*.java)
SERVICE_DEVICE_CONFIG = 0x01
SERVICE_FITNESS_DATA = 0x07
SERVICE_WORKOUT = 0x19
SERVICE_ACCOUNT = 0x1A
SERVICE_FILE_DOWNLOAD_2C = 0x2C

# DeviceConfig commands
CMD_LINK_PARAMS = 0x01
CMD_SUPPORTED_SERVICES = 0x02
CMD_SUPPORTED_COMMANDS = 0x03
CMD_AUTH = 0x05
CMD_BOND_PARAMS = 0x0B
CMD_SECURITY_NEGOTIATION = 0x33
CMD_CONNECT_STATUS = 0x35
CMD_EXPAND_CAPABILITY = 0x37

# FitnessData commands (confirmed by Gadgetbridge source; not yet exercised
# against this Band 9 in this repository)
CMD_ENABLE_AUTOMATIC_HR = 0x17
CMD_NOTIFY_REST_HR = 0x23
CMD_ENABLE_AUTOMATIC_SPO = 0x24

AUTH_TYPE_HICHAIN = 0x0186A0
AUTH_TYPE_HICHAIN_LITE = {0x01, 0x02}
AUTH_TYPE_HICHAIN3 = {0x04, 0x05, 0x06}


class ProtocolError(ValueError):
    """Raised when a frame or TLV cannot be decoded safely."""


def crc16(data: bytes) -> int:
    """CRC16-HQXQ (poly 0x1021, init 0) used by Huawei Link Protocol."""
    return binascii.crc_hqx(data, 0) & 0xFFFF


def crc16_bytes(data: bytes) -> bytes:
    return crc16(data).to_bytes(2, "big")


def encode_varint(value: int) -> bytes:
    """Encode a Huawei TLV length as a big-endian base-128 varint.

    Huawei's encoder emits at least one byte, including for zero-length values
    (``00``). This differs from some early third-party implementations.
    """
    if value < 0:
        raise ValueError("varint must be non-negative")
    if value == 0:
        return b"\x00"
    out = bytearray()
    while value:
        out.append(value & 0x7F)
        value >>= 7
    out.reverse()
    for i in range(len(out) - 1):
        out[i] |= 0x80
    return bytes(out)


def decode_varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    """Decode a base-128 varint and return ``(value, new_offset)``."""
    value = 0
    i = offset
    while i < len(data):
        byte = data[i]
        i += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, i
    raise ProtocolError("truncated varint")


@dataclass(frozen=True)
class TLV:
    tag: int
    value: bytes = b""

    def to_bytes(self) -> bytes:
        return bytes([self.tag]) + encode_varint(len(self.value)) + self.value

    @classmethod
    def parse_all(cls, data: bytes) -> list[TLV]:
        tlvs: list[TLV] = []
        offset = 0
        while offset < len(data):
            tag = data[offset]
            offset += 1
            length, offset = decode_varint(data, offset)
            end = offset + length
            if end > len(data):
                raise ProtocolError(
                    f"TLV 0x{tag:02x} length {length} exceeds remaining {len(data) - offset} bytes"
                )
            tlvs.append(cls(tag, data[offset:end]))
            offset = end
        return tlvs


def encode_tlvs(tlvs: Iterable[TLV]) -> bytes:
    return b"".join(tlv.to_bytes() for tlv in tlvs)


@dataclass(frozen=True)
class Frame:
    """One complete (already BLE-reassembled) LP frame."""

    slice_type: int
    payload: bytes
    raw: bytes

    @property
    def service_id(self) -> int | None:
        return self.payload[0] if self.slice_type == 0 and len(self.payload) >= 2 else None

    @property
    def command_id(self) -> int | None:
        return self.payload[1] if self.slice_type == 0 and len(self.payload) >= 2 else None

    @property
    def tlvs(self) -> list[TLV]:
        if self.slice_type != 0:
            return []
        return TLV.parse_all(self.payload[2:])


def build_frame(service_id: int, command_id: int, tlvs: Iterable[TLV]) -> bytes:
    """Serialize an unsliced LP frame.

    This is the CONFIRMED layout used by the LinkParams handshake:
    ``5A LL LL 00 SS CC <tlv...> CRC CRC`` where ``LLLL`` equals
    ``len(service_id + command_id + tlv_bytes) + 1``.
    """
    payload = bytes([service_id, command_id]) + encode_tlvs(tlvs)
    header = bytes([MAGIC]) + (len(payload) + 1).to_bytes(2, "big") + b"\x00"
    body = header + payload
    return body + crc16_bytes(body)


def build_link_params_request() -> bytes:
    """CONFIRMED request: four empty TLVs 0x01..0x04.

    Produces ``5A 00 0B 00 01 01 01 00 02 00 03 00 04 00 F1 3B``, matching
    the frame published by Kudera (2019) for LPv2.
    """
    return build_frame(
        SERVICE_DEVICE_CONFIG,
        CMD_LINK_PARAMS,
        [TLV(0x01), TLV(0x02), TLV(0x03), TLV(0x04)],
    )


class FrameDecoder:
    """Reassemble BLE notification fragments into LP frames.

    BlueZ normally delivers a full GATT notification, but a notification may
    itself contain multiple LP frames or a partial frame. This buffer handles
    both. Large LP payloads split by Huawei's own slicing layer are collected
    and exposed as a synthetic unsliced frame (HYPOTHESIS, not yet exercised).
    """

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._slices: list[bytes] = []
        self._slice_flag: int | None = None

    def feed(self, data: bytes) -> Iterator[Frame]:
        self._buffer.extend(data)
        while True:
            if len(self._buffer) < HEADER_SIZE + CRC_SIZE:
                return
            if self._buffer[0] != MAGIC:
                # Resynchronise on the next magic byte rather than silently
                # decoding garbage. Keep the discarded bytes in raw output.
                idx = self._buffer.find(bytes([MAGIC]), 1)
                if idx == -1:
                    self._buffer.clear()
                    return
                del self._buffer[:idx]
                continue
            length = int.from_bytes(self._buffer[1:3], "big")
            total = length + 5  # magic+len+slice (4) + payload (length-1) + crc (2)
            if len(self._buffer) < total:
                return
            raw = bytes(self._buffer[:total])
            body, expected = raw[:-2], raw[-2:]
            if crc16_bytes(body) != expected:
                raise ProtocolError(
                    f"CRC mismatch: got {expected.hex()} expected {crc16_bytes(body).hex()}"
                )
            slice_type = raw[3]
            if slice_type == 0:
                yield Frame(slice_type, raw[4:-2], raw)
            else:
                frame = self._feed_slice(slice_type, raw[4:-2], raw)
                if frame is not None:
                    yield frame
            del self._buffer[:total]

    def _feed_slice(self, slice_type: int, content: bytes, raw: bytes) -> Frame | None:
        if slice_type == 1:
            self._slices = [content]
            self._slice_flag = content[0] if content else None
            return None
        if not self._slices:
            return None
        self._slices.append(content)
        if slice_type != 3:
            return None
        first = self._slices[0]
        # First slice: flag byte + service + command + TLV. Later slices: TLV.
        payload = first[1:] + b"".join(part for part in self._slices[1:])
        synthetic = bytes([MAGIC]) + (len(payload) + 1).to_bytes(2, "big") + b"\x00" + payload
        synthetic += crc16_bytes(synthetic)
        self._slices = []
        self._slice_flag = None
        return Frame(0, payload, raw + synthetic)


# --- LinkParams response ---------------------------------------------------
@dataclass
class LinkParams:
    protocol_version: int | None = None
    slice_size: int | None = None
    mtu: int | None = None
    connection_interval: int | None = None
    auth_version: int | None = None
    server_nonce: bytes | None = None
    device_support_type: int | None = None
    auth_algo: int | None = None
    bond_state: int | None = None
    encrypt_method: int | None = None
    raw_tlvs: list[TLV] = field(default_factory=list)

    @classmethod
    def from_tlvs(cls, tlvs: Iterable[TLV]) -> LinkParams:
        values = {tlv.tag: tlv.value for tlv in tlvs}
        out = cls(raw_tlvs=list(tlvs))

        def byte(tag: int) -> int | None:
            return values[tag][0] if tag in values and len(values[tag]) >= 1 else None

        def short(tag: int) -> int | None:
            return int.from_bytes(values[tag], "big") if tag in values and len(values[tag]) >= 2 else None

        out.protocol_version = byte(0x01)
        out.slice_size = short(0x02)
        out.mtu = short(0x03)
        out.connection_interval = short(0x04)
        nonce = values.get(0x05, b"")
        if len(nonce) >= 18:
            out.auth_version = nonce[1]
            out.server_nonce = nonce[2:18]
        elif len(nonce) >= 2:
            out.auth_version = nonce[1]
            out.server_nonce = nonce[2:]
        out.device_support_type = byte(0x07)
        out.auth_algo = byte(0x08)
        out.bond_state = byte(0x09)
        out.encrypt_method = byte(0x0C)
        return out

    def auth_family(self) -> str:
        if self.device_support_type == 4:
            return "HiChain3 (deviceSupportType=4)"
        if self.device_support_type == 2:
            return "HiChain Lite (deviceSupportType=2)"
        if self.device_support_type in (1, 3):
            return f"HiChain (deviceSupportType={self.device_support_type})"
        return f"unknown (deviceSupportType={self.device_support_type})"

    def to_dict(self) -> dict:
        return {
            "protocol_version": self.protocol_version,
            "slice_size": self.slice_size,
            "mtu": self.mtu,
            "connection_interval": self.connection_interval,
            "auth_version": self.auth_version,
            "server_nonce_hex": self.server_nonce.hex() if self.server_nonce else None,
            "device_support_type": self.device_support_type,
            "auth_family": self.auth_family(),
            "auth_algo": self.auth_algo,
            "bond_state": self.bond_state,
            "encrypt_method": self.encrypt_method,
            "tlvs": [{"tag": f"0x{t.tag:02x}", "value_hex": t.value.hex()} for t in self.raw_tlvs],
        }


def classify_auth_type(auth_type: int | None) -> str:
    if auth_type is None:
        return "unknown"
    if auth_type == AUTH_TYPE_HICHAIN:
        return "HiChain"
    if auth_type in AUTH_TYPE_HICHAIN_LITE:
        return f"HiChain Lite (authType=0x{auth_type:02x})"
    if auth_type in AUTH_TYPE_HICHAIN3:
        return f"HiChain3 (authType=0x{auth_type:02x})"
    return f"unknown (authType=0x{auth_type:02x})"
