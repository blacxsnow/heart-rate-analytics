"""Tests for the HOTA container parser (synthetic packages only)."""

from __future__ import annotations

import hashlib

import pytest

from fitness_band.hota import (
    ENTRY_LEN,
    MANIFEST_OFFSET,
    VERSION_OFFSET,
    HotaError,
    extract,
    parse_hota,
    verify_entries,
)

SIG_OFFSET = 0x11C1
PAYLOAD_OFFSET = 0x1341
TAG_OFFSET = 0x0C


def build_package(files: list[tuple[str, bytes]]) -> bytes:
    header = bytearray(PAYLOAD_OFFSET)

    header[0:2] = (1).to_bytes(2, "little")
    header[2:4] = (0x88).to_bytes(2, "little")
    header[4:8] = SIG_OFFSET.to_bytes(4, "little")
    header[8:12] = (1).to_bytes(4, "little")
    header[TAG_OFFSET : TAG_OFFSET + 4] = b"Kimi"
    header[VERSION_OFFSET : VERSION_OFFSET + 16] = b"4.2.0.230(C00M07)"
    header[0x8C:0x8E] = (2).to_bytes(2, "little")
    header[0x8E:0x90] = (0x20).to_bytes(2, "little")
    header[0x90:0x9B] = b"2026.08.28"
    header[0xA0:0xA8] = b"12:06:45"
    header[MANIFEST_OFFSET : MANIFEST_OFFSET + 2] = (5).to_bytes(2, "little")
    header[MANIFEST_OFFSET + 2 : MANIFEST_OFFSET + 4] = (len(files) * ENTRY_LEN).to_bytes(
        2, "little"
    )

    for i, (name, blob) in enumerate(files):
        base = MANIFEST_OFFSET + 4 + i * ENTRY_LEN
        encoded = name.encode()
        assert len(encoded) < 64
        header[base : base + len(encoded)] = encoded
        header[base + 0x7C : base + 0x82] = b"\x00\x01\x00\x01\x00\x00"
        header[base + 0x82 : base + 0x8C] = b"0.0.0.0\x00\x00\x00"
        header[base + 0x8C : base + 0x90] = len(blob).to_bytes(4, "little")
        header[base + 0x90 : base + 0x94] = (0).to_bytes(4, "little")
        header[base + 0x94 : base + 0xB4] = hashlib.sha256(blob).digest()
        header[base + 0xB4 : base + 0xD4] = bytes(range(32))

    header[SIG_OFFSET:PAYLOAD_OFFSET] = b"\xaa" * (PAYLOAD_OFFSET - SIG_OFFSET)
    return bytes(header) + b"".join(blob for _, blob in files)


FILES = [
    ("/system/res/boot.bin", b"BOOT" * 100),
    ("/system/config/cak.bin", b"key" * 10),
]


def test_parse_synthetic_package() -> None:
    data = build_package(FILES)
    pkg = parse_hota(data)

    assert pkg.tag == "Kimi"
    assert pkg.version == "4.2.0.230(C00M07)"
    assert pkg.build_time == "2026.08.28 12:06:45"
    assert pkg.signature_offset == SIG_OFFSET
    assert len(pkg.signature) == PAYLOAD_OFFSET - SIG_OFFSET
    assert pkg.data_offset == PAYLOAD_OFFSET
    assert [e.name for e in pkg.entries] == [name for name, _ in FILES]
    assert [e.size for e in pkg.entries] == [len(blob) for _, blob in FILES]
    assert verify_entries(data, pkg) == [True, True]


def test_tampered_payload_fails_verification(tmp_path) -> None:
    data = bytearray(build_package(FILES))
    data[-1] ^= 0xFF

    pkg = parse_hota(bytes(data))
    assert verify_entries(bytes(data), pkg) == [True, False]
    with pytest.raises(HotaError):
        extract(bytes(data), pkg, tmp_path)


def test_extract_writes_verified_files(tmp_path) -> None:
    data = build_package(FILES)
    pkg = parse_hota(data)

    written = extract(data, pkg, tmp_path)

    assert len(written) == 2
    assert (tmp_path / "system/res/boot.bin").read_bytes() == FILES[0][1]
    assert (tmp_path / "system/config/cak.bin").read_bytes() == FILES[1][1]


def test_rejects_unknown_layout() -> None:
    data = bytearray(build_package(FILES))
    data[0:2] = (9).to_bytes(2, "little")

    with pytest.raises(HotaError):
        parse_hota(bytes(data))
