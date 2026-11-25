from __future__ import annotations

import pytest

from fitness_band.protocol import (
    CMD_LINK_PARAMS,
    SERVICE_DEVICE_CONFIG,
    TLV,
    FrameDecoder,
    LinkParams,
    ProtocolError,
    build_frame,
    build_link_params_request,
    classify_auth_type,
    crc16,
    crc16_bytes,
    decode_varint,
    encode_tlvs,
    encode_varint,
)


def test_crc16_known_value():
    # CRC of the documented LinkParams frame body.
    body = bytes.fromhex("5a000b0001010100020003000400")
    assert crc16(body) == 0xF13B


def test_link_params_request_matches_published_frame():
    assert build_link_params_request().hex() == "5a000b0001010100020003000400f13b"


def test_build_frame_roundtrip():
    raw = build_frame(SERVICE_DEVICE_CONFIG, CMD_LINK_PARAMS, [TLV(1), TLV(2, b"\xaa")])
    decoder = FrameDecoder()
    frames = list(decoder.feed(raw))
    assert len(frames) == 1
    frame = frames[0]
    assert frame.service_id == SERVICE_DEVICE_CONFIG
    assert frame.command_id == CMD_LINK_PARAMS
    assert frame.tlvs == [TLV(1), TLV(2, b"\xaa")]


def test_decoder_handles_fragmented_and_concatenated_frames():
    raw = build_link_params_request() * 2
    decoder = FrameDecoder()
    assert list(decoder.feed(raw[:5])) == []
    frames = list(decoder.feed(raw[5:]))
    assert len(frames) == 2


def _slice_frame(slice_type: int, content: bytes) -> bytes:
    body = (
        bytes([0x5A])
        + (len(content) + 1).to_bytes(2, "big")
        + bytes([slice_type])
        + content
    )
    return body + crc16_bytes(body)


def test_sliced_frame_reassembly_strips_sequence_bytes():
    payload = bytes([SERVICE_DEVICE_CONFIG, CMD_LINK_PARAMS]) + encode_tlvs(
        [TLV(1), TLV(2, b"x" * 400)]
    )
    chunks = [payload[:200], payload[200:400], payload[400:]]
    raw = (
        _slice_frame(1, b"\x00" + chunks[0])
        + _slice_frame(2, b"\x01" + chunks[1])
        + _slice_frame(3, b"\x02" + chunks[2])
    )

    frames = list(FrameDecoder().feed(raw))

    assert len(frames) == 1
    assert frames[0].payload == payload
    assert frames[0].service_id == SERVICE_DEVICE_CONFIG
    assert frames[0].command_id == CMD_LINK_PARAMS


def test_bad_crc_rejected():
    raw = bytearray(build_link_params_request())
    raw[-1] ^= 0xFF
    with pytest.raises(ProtocolError):
        list(FrameDecoder().feed(bytes(raw)))


@pytest.mark.parametrize(
    "value,encoded",
    [
        (0, "00"),
        (1, "01"),
        (127, "7f"),
        (128, "8100"),
        (300, "822c"),
    ],
)
def test_varint_roundtrip(value, encoded):
    raw = encode_varint(value)
    assert raw.hex() == encoded
    assert decode_varint(raw) == (value, len(raw))


def test_link_params_response_parse():
    nonce = bytes(range(16))
    tlvs = [
        TLV(0x01, b"\x02"),
        TLV(0x02, (0xF4).to_bytes(2, "big")),
        TLV(0x03, (0x0014).to_bytes(2, "big")),
        TLV(0x04, (0x000A).to_bytes(2, "big")),
        TLV(0x05, b"\x00\x02" + nonce),
        TLV(0x07, b"\x02"),
        TLV(0x08, b"\x00"),
        TLV(0x09, b"\x01"),
        TLV(0x0C, b"\x00"),
    ]
    params = LinkParams.from_tlvs(tlvs)
    assert params.protocol_version == 2
    assert params.slice_size == 0xF4
    assert params.mtu == 20
    assert params.auth_version == 2
    assert params.server_nonce == nonce
    assert params.device_support_type == 2
    assert "HiChain Lite" in params.auth_family()
    assert params.bond_state == 1


def test_auth_type_classification():
    assert classify_auth_type(0x0186A0).startswith("HiChain")
    assert "Lite" in classify_auth_type(1)
    assert "HiChain3" in classify_auth_type(5)
