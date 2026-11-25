"""Tests for the partial fitness-history envelope decoder (synthetic data)."""

from __future__ import annotations

import pytest

from fitness_band.history import HistoryError, parse_sample_batch, parse_status_batch
from fitness_band.protocol import TLV, encode_tlvs


def test_parse_sample_batch() -> None:
    minute = encode_tlvs(
        [
            TLV(0x05, b"\x00"),
            TLV(0x06, b"\x0e\x00"),
            TLV(0x07, b"\x00\x00\x00\xf0"),
            TLV(0x08, b"\x00\x00"),
        ]
    )
    inner = encode_tlvs(
        [
            TLV(0x02, b"\x00\x00"),
            TLV(0x03, (1_700_000_000).to_bytes(4, "big")),
            TLV(0x84, minute),
            TLV(0x08, b"\x00"),
        ]
    )
    batch = parse_sample_batch(TLV(0x81, inner).to_bytes())

    assert batch.status == 0
    assert batch.start_time == 1_700_000_000
    assert len(batch.records) == 1
    record = batch.records[0]
    assert record.minute == 0
    assert record.field(0x06) == b"\x0e\x00"
    assert record.field(0x07) == b"\x00\x00\x00\xf0"
    assert record.field(0x45) is None
    assert [tlv.tag for tlv in batch.trailer] == [0x08]


def test_parse_status_batch() -> None:
    record = encode_tlvs(
        [
            TLV(0x04, b"\x01"),
            TLV(0x05, (1_700_000_000).to_bytes(4, "big") + b"\x00\x01"),
            TLV(0x06, b"\x00"),
        ]
    )
    inner = encode_tlvs([TLV(0x02, b"\x00\x00"), TLV(0x83, record)])
    batch = parse_status_batch(TLV(0x81, inner).to_bytes())

    assert batch.status == 0
    assert len(batch.records) == 1
    assert batch.records[0].field(0x04) == b"\x01"
    assert batch.records[0].field(0x05) == ((1_700_000_000).to_bytes(4, "big") + b"\x00\x01")


def test_missing_array_rejected() -> None:
    with pytest.raises(HistoryError):
        parse_sample_batch(TLV(0x02, b"\x00").to_bytes())


def test_invalid_nested_record_rejected() -> None:
    inner = encode_tlvs([TLV(0x84, b"\x05\x02\x00")])  # length 2, only 1 byte
    with pytest.raises(HistoryError):
        parse_sample_batch(TLV(0x81, inner).to_bytes())
