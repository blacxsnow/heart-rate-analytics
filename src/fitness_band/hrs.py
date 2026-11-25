"""Standard Bluetooth Heart Rate Service (0x180D / 0x2A37) decoding.

This is the only physiological path that has been verified end-to-end against
the physical Band 9 in this project. The Band 9 emits one notification per
second with flags 0x06 (uint8 heart rate, skin contact supported and detected)
and no RR-interval field.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FLAG_UINT16 = 0x01
FLAG_CONTACT_SUPPORTED = 0x02
FLAG_CONTACT_DETECTED = 0x04
FLAG_ENERGY_EXPENDED = 0x08
FLAG_RR_INTERVALS = 0x10


class HeartRateParseError(ValueError):
    pass


@dataclass(frozen=True)
class HeartRateMeasurement:
    heart_rate_bpm: int
    sensor_contact: bool | None
    energy_expended_kj: int | None
    rr_intervals_s: list[float] = field(default_factory=list)
    flags: int = 0

    @property
    def rr_intervals_ms(self) -> list[float]:
        return [round(value * 1000.0, 3) for value in self.rr_intervals_s]

    def to_dict(self) -> dict:
        return {
            "heart_rate_bpm": self.heart_rate_bpm,
            "sensor_contact": self.sensor_contact,
            "energy_expended_kj": self.energy_expended_kj,
            "rr_intervals_s": self.rr_intervals_s,
            "rr_intervals_ms": self.rr_intervals_ms,
            "flags": self.flags,
        }


def parse_heart_rate_measurement(data: bytes | bytearray) -> HeartRateMeasurement:
    """Decode a 0x2A37 notification.

    Raises :class:`HeartRateParseError` on truncated or implausible payloads so
    that a malformed packet is stored raw but never presented as a measurement.
    """
    data = bytes(data)
    if not data:
        raise HeartRateParseError("empty heart-rate notification")

    flags = data[0]
    offset = 1

    if flags & FLAG_UINT16:
        if len(data) < offset + 2:
            raise HeartRateParseError("truncated uint16 heart rate")
        heart_rate = int.from_bytes(data[offset : offset + 2], "little")
        offset += 2
    else:
        if len(data) < offset + 1:
            raise HeartRateParseError("truncated uint8 heart rate")
        heart_rate = data[offset]
        offset += 1

    if not 0 <= heart_rate <= 65535:
        raise HeartRateParseError(f"implausible heart rate {heart_rate}")

    if flags & FLAG_CONTACT_SUPPORTED:
        sensor_contact: bool | None = bool(flags & FLAG_CONTACT_DETECTED)
    else:
        sensor_contact = None

    energy: int | None = None
    if flags & FLAG_ENERGY_EXPENDED:
        if len(data) < offset + 2:
            raise HeartRateParseError("truncated energy expended")
        energy = int.from_bytes(data[offset : offset + 2], "little")
        offset += 2

    rr: list[float] = []
    if flags & FLAG_RR_INTERVALS:
        remaining = len(data) - offset
        if remaining < 2 or remaining % 2:
            raise HeartRateParseError("truncated RR interval list")
        for i in range(offset, len(data), 2):
            raw = int.from_bytes(data[i : i + 2], "little")
            rr.append(raw / 1024.0)

    return HeartRateMeasurement(
        heart_rate_bpm=heart_rate,
        sensor_contact=sensor_contact,
        energy_expended_kj=energy,
        rr_intervals_s=rr,
        flags=flags,
    )
