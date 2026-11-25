"""Tests for the offline proprietary-channel helpers."""

from __future__ import annotations

import pytest

from fitness_band.proprietary import (
    TAG_ENCRYPTION_FLAG,
    TAG_GCM_CIPHERTEXT,
    TAG_GCM_IV,
    auto_hr_frame,
    auto_spo2_frame,
    decrypt_tlv_block,
    encrypt_tlv_block,
    hr_alert_high_frame,
    security_negotiation_request,
    spo2_alert_frame,
    today_total_frame,
    wrap_frame,
)
from fitness_band.protocol import TLV, FrameDecoder, ProtocolError

KEY = bytes(range(16))
IV = bytes(range(0x40, 0x50))


def decode_frame(raw: bytes):
    frames = list(FrameDecoder().feed(raw))
    assert len(frames) == 1
    return frames[0]


def test_auto_hr_frame_matches_confirmed_shape() -> None:
    frame = decode_frame(auto_hr_frame(True))
    assert frame.service_id == 0x07
    assert frame.command_id == 0x17
    assert [(t.tag, t.value) for t in frame.tlvs] == [(0x01, b"\x01")]

    off = decode_frame(auto_hr_frame(False))
    assert [(t.tag, t.value) for t in off.tlvs] == [(0x01, b"\x00")]


def test_auto_spo2_and_today_and_alerts() -> None:
    spo2 = decode_frame(auto_spo2_frame(True))
    assert (spo2.service_id, spo2.command_id) == (0x07, 0x24)

    total = decode_frame(today_total_frame())
    assert (total.service_id, total.command_id) == (0x07, 0x03)
    assert [(t.tag, t.value) for t in total.tlvs] == [(0x01, b"")]

    high = decode_frame(hr_alert_high_frame(120))
    assert (high.service_id, high.command_id) == (0x07, 0x1D)
    assert [(t.tag, t.value) for t in high.tlvs] == [
        (0x01, b"\x01"),
        (0x02, b"\x78"),
    ]

    low = decode_frame(spo2_alert_frame(90))
    assert (low.service_id, low.command_id) == (0x07, 0x25)
    assert [(t.tag, t.value) for t in low.tlvs] == [
        (0x01, b"\x01"),
        (0x02, b"\x5a"),
    ]


def test_gcm_envelope_roundtrip() -> None:
    plaintext = b"\x01\x01\x01"
    tlvs = encrypt_tlv_block(plaintext, KEY, iv=IV)

    assert [t.tag for t in tlvs] == [TAG_ENCRYPTION_FLAG, TAG_GCM_IV, TAG_GCM_CIPHERTEXT]
    assert tlvs[0].value == b"\x01"
    assert tlvs[1].value == IV
    assert len(tlvs[2].value) == len(plaintext) + 16

    assert decrypt_tlv_block(tlvs, KEY) == plaintext


def test_gcm_envelope_rejects_tampering() -> None:
    tlvs = encrypt_tlv_block(b"payload", KEY, iv=IV)
    tampered = list(tlvs)
    tampered[2] = TLV(TAG_GCM_CIPHERTEXT, tlvs[2].value[:-1] + bytes([tlvs[2].value[-1] ^ 1]))

    with pytest.raises(ProtocolError):
        decrypt_tlv_block(tampered, KEY)


def test_wrap_frame_encrypts_tlv_block() -> None:
    raw = wrap_frame(0x07, 0x17, [TLV(0x01, b"\x01")], key=KEY, iv=IV)
    frame = decode_frame(raw)
    assert (frame.service_id, frame.command_id) == (0x07, 0x17)
    assert [t.tag for t in frame.tlvs] == [
        TAG_ENCRYPTION_FLAG,
        TAG_GCM_IV,
        TAG_GCM_CIPHERTEXT,
    ]
    assert decrypt_tlv_block(frame.tlvs, KEY) == b"\x01\x01\x01"


def test_security_negotiation_request_fields() -> None:
    frame = decode_frame(security_negotiation_request(b"\x11" * 16, "Test Phone"))
    assert (frame.service_id, frame.command_id) == (0x01, 0x33)
    values = {t.tag: t.value for t in frame.tlvs}
    assert values[0x01] == b"\x04"
    assert values[0x02] == b"\x01"
    assert values[0x05] == b"\x11" * 16
    assert values[0x06] == b"phoneIdentify"
    assert values[0x07] == b"Test Phone"
