"""Parser for Huawei HOTA wearable firmware containers.

The container is the file that Huawei Health downloads from
``update.hicloud.com`` and hands to the band. It is not a zip/apk despite the
``.bin.apk`` suffix: it is a small header, a component manifest, a detached
signature block and a concatenation of full component images.

Only the version-1 layout observed on the Band 9 package
``Kimi_DIFF_4.2.0.226(C00M06)-4.2.0.230(C00M07).bin.apk`` is implemented:

====================  ====================================================
offset                field
====================  ====================================================
0x00                  u16 layout version (1)
0x02                  u16 header length (0x88)
0x04                  u32 signature offset
0x08                  u32 unknown (1 in the observed package)
0x0c                  char[64] product tag ("Kimi")
0x4c                  char[64] package version
0x8c                  u16 tag (2), u16 length (0x20), build date + time
0xb0                  u16 tag (5), u16 manifest length
0xb4                  manifest entries, 0xd4 bytes each
...                   signature block (signature offset .. payload)
payload               component images, in manifest order
====================  ====================================================

Manifest entry (0xd4 bytes)::

    char name[64]; u8 reserved[60]; u8 flags[6]; char version[10];
    u32 size; u32 crc32; u8 sha256[32]; u8 source_digest[32]

``sha256`` is verified against the payload slice. ``source_digest`` is not the
MD5 of the payload and is believed to identify the previous (source) file in a
file-level diff package; it is kept opaque here.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

HEADER_LEN = 0xB4
ENTRY_LEN = 0xD4
TAG_OFFSET = 0x0C
TAG_LEN = 64
VERSION_OFFSET = 0x4C
VERSION_LEN = 64
DATE_OFFSET = 0x90
DATE_LEN = 11
TIME_OFFSET = 0xA0
TIME_LEN = 8
SIG_OFFSET_FIELD = 0x04
MANIFEST_OFFSET = 0xB0


class HotaError(ValueError):
    """Raised when the container does not match the expected layout."""


@dataclass
class HotaEntry:
    name: str
    version: str
    size: int
    crc32: int
    sha256: str
    source_digest: str
    flags: bytes
    data_offset: int
    verified: bool | None = None

    @property
    def basename(self) -> str:
        return self.name.rsplit("/", 1)[-1]


@dataclass
class HotaPackage:
    layout_version: int
    tag: str
    version: str
    build_time: str
    signature_offset: int
    signature: bytes
    entries: list[HotaEntry] = field(default_factory=list)
    data_offset: int = 0

    @property
    def component_bytes(self) -> int:
        return sum(e.size for e in self.entries)

    def entry(self, name: str) -> HotaEntry:
        for e in self.entries:
            if e.name == name or e.basename == name:
                return e
        raise KeyError(name)


def _text(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("utf-8", "replace")


def parse_hota(data: bytes) -> HotaPackage:
    """Parse a HOTA container from ``data``.

    Raises :class:`HotaError` if the header/manifest does not fit.
    """

    if len(data) < HEADER_LEN:
        raise HotaError("file shorter than HOTA header")

    layout_version = int.from_bytes(data[0:2], "little")
    header_len = int.from_bytes(data[2:4], "little")
    if layout_version != 1 or header_len != 0x88:
        raise HotaError(f"unsupported HOTA layout {layout_version}/{header_len:#x}")

    sig_offset = int.from_bytes(data[SIG_OFFSET_FIELD : SIG_OFFSET_FIELD + 4], "little")
    tag = _text(data[TAG_OFFSET : TAG_OFFSET + TAG_LEN])
    version = _text(data[VERSION_OFFSET : VERSION_OFFSET + VERSION_LEN])
    build_time = (
        _text(data[DATE_OFFSET : DATE_OFFSET + DATE_LEN])
        + " "
        + _text(data[TIME_OFFSET : TIME_OFFSET + TIME_LEN])
    )

    if int.from_bytes(data[MANIFEST_OFFSET : MANIFEST_OFFSET + 2], "little") != 5:
        raise HotaError("manifest tag missing")

    manifest_len = int.from_bytes(data[MANIFEST_OFFSET + 2 : MANIFEST_OFFSET + 4], "little")
    if manifest_len % ENTRY_LEN:
        raise HotaError(f"manifest length {manifest_len} is not a multiple of {ENTRY_LEN}")

    entries: list[HotaEntry] = []
    for i in range(manifest_len // ENTRY_LEN):
        base = MANIFEST_OFFSET + 4 + i * ENTRY_LEN
        chunk = data[base : base + ENTRY_LEN]
        if len(chunk) != ENTRY_LEN:
            raise HotaError("truncated manifest")

        entries.append(
            HotaEntry(
                name=_text(chunk[0:64]),
                flags=chunk[0x7C:0x82],
                version=_text(chunk[0x82:0x8C]),
                size=int.from_bytes(chunk[0x8C:0x90], "little"),
                crc32=int.from_bytes(chunk[0x90:0x94], "little"),
                sha256=chunk[0x94:0xB4].hex(),
                source_digest=chunk[0xB4:0xD4].hex(),
                data_offset=0,
            )
        )

    payload = sum(e.size for e in entries)
    data_offset = len(data) - payload
    if data_offset < sig_offset:
        raise HotaError("payload overlaps signature block")

    cursor = data_offset
    for e in entries:
        e.data_offset = cursor
        cursor += e.size
    if cursor != len(data):
        raise HotaError("payload does not end at end of file")

    return HotaPackage(
        layout_version=layout_version,
        tag=tag,
        version=version,
        build_time=build_time,
        signature_offset=sig_offset,
        signature=data[sig_offset:data_offset],
        entries=entries,
        data_offset=data_offset,
    )


def verify_entries(data: bytes, package: HotaPackage) -> list[bool]:
    """Check each manifest SHA-256 against its payload slice."""

    results: list[bool] = []
    for e in package.entries:
        blob = data[e.data_offset : e.data_offset + e.size]
        digest = hashlib.sha256(blob).hexdigest()
        e.verified = len(blob) == e.size and digest == e.sha256
        results.append(e.verified)
    return results


def extract(data: bytes, package: HotaPackage, out_dir: Path) -> list[Path]:
    """Write every verified component under ``out_dir`` using its manifest path."""

    written: list[Path] = []
    for e in package.entries:
        blob = data[e.data_offset : e.data_offset + e.size]
        if hashlib.sha256(blob).hexdigest() != e.sha256:
            raise HotaError(f"SHA-256 mismatch for {e.name}")
        rel = e.name.lstrip("/")
        target = out_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
        written.append(target)
    return written
