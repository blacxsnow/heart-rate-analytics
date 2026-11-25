"""Partial decoder for Huawei fitness-history envelopes (0x07/0x0B, 0x0D).

The outer structure is confirmed from the 2026-11-25 authenticated capture: a
``0x81`` array containing a status TLV, a start timestamp, a sequence of
``0x84`` minute records and a trailer. Each ``0x84`` value is itself a TLV
list (``0x05`` minute index, ``0x06`` payload, optional ``0x07``/``0x08``).

Field semantics inside ``0x06``/``0x07``/``0x08`` are **not** fully decoded;
this module preserves them as raw TLVs so downstream code can store and later
annotate them without guessing. Do not treat this as a complete health-record
decoder.
"""

from __future__ import annotations

from dataclasses import dataclass

from .protocol import TLV, ProtocolError


class HistoryError(ValueError):
    """Raised when a history envelope does not match the confirmed shape."""


@dataclass(frozen=True)
class MinuteRecord:
    minute: int | None
    fields: tuple[TLV, ...]
    raw: bytes

    def field(self, tag: int) -> bytes | None:
        for item in self.fields:
            if item.tag == tag:
                return item.value
        return None


@dataclass(frozen=True)
class SampleBatch:
    status: int | None
    start_time: int | None
    records: tuple[MinuteRecord, ...]
    trailer: tuple[TLV, ...]
    raw: bytes


@dataclass(frozen=True)
class StatusRecord:
    fields: tuple[TLV, ...]
    raw: bytes

    def field(self, tag: int) -> bytes | None:
        for item in self.fields:
            if item.tag == tag:
                return item.value
        return None


@dataclass(frozen=True)
class StatusBatch:
    status: int | None
    records: tuple[StatusRecord, ...]
    trailer: tuple[TLV, ...]
    raw: bytes


def _outer_array(payload: bytes) -> tuple[list[TLV], bytes]:
    outer = TLV.parse_all(payload)
    for item in outer:
        if item.tag == 0x81:
            return TLV.parse_all(item.value), item.value
    raise HistoryError("missing 0x81 array")


def _small_int(value: bytes | None) -> int | None:
    if value is None or not 1 <= len(value) <= 4:
        return None
    return int.from_bytes(value, "big")


def parse_sample_batch(payload: bytes) -> SampleBatch:
    """Parse a 0x07/0x0B minute-record batch (envelope confirmed)."""

    try:
        inner, array = _outer_array(payload)
    except ProtocolError as exc:
        raise HistoryError(f"invalid TLV: {exc}") from exc

    status_value: bytes | None = None
    start_value: bytes | None = None
    records: list[MinuteRecord] = []
    trailer: list[TLV] = []

    for item in inner:
        if item.tag == 0x02:
            status_value = item.value
        elif item.tag == 0x03 and len(item.value) == 4:
            start_value = item.value
        elif item.tag == 0x84:
            try:
                fields = TLV.parse_all(item.value)
            except ProtocolError as exc:
                raise HistoryError(f"invalid 0x84 record: {exc}") from exc
            minute = next(
                (field.value[0] for field in fields if field.tag == 0x05 and len(field.value) == 1),
                None,
            )
            records.append(MinuteRecord(minute, tuple(fields), item.value))
        else:
            trailer.append(item)

    return SampleBatch(
        status=_small_int(status_value),
        start_time=_small_int(start_value),
        records=tuple(records),
        trailer=tuple(trailer),
        raw=array,
    )


def parse_status_batch(payload: bytes) -> StatusBatch:
    """Parse a 0x07/0x0D status-record batch (envelope confirmed)."""

    try:
        inner, array = _outer_array(payload)
    except ProtocolError as exc:
        raise HistoryError(f"invalid TLV: {exc}") from exc

    status_value: bytes | None = None
    records: list[StatusRecord] = []
    trailer: list[TLV] = []

    for item in inner:
        if item.tag == 0x02:
            status_value = item.value
        elif item.tag == 0x83:
            try:
                fields = TLV.parse_all(item.value)
            except ProtocolError as exc:
                raise HistoryError(f"invalid 0x83 record: {exc}") from exc
            records.append(StatusRecord(tuple(fields), item.value))
        else:
            trailer.append(item)

    return StatusBatch(
        status=_small_int(status_value),
        records=tuple(records),
        trailer=tuple(trailer),
        raw=array,
    )


__all__ = [
    "HistoryError",
    "MinuteRecord",
    "SampleBatch",
    "StatusBatch",
    "StatusRecord",
    "parse_sample_batch",
    "parse_status_batch",
]
