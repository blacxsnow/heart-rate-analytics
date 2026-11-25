#!/usr/bin/env python3
"""Minimal btsnoop + HCI ACL + L2CAP/ATT extractor.

Android's Bluetooth HCI snoop log is btsnoop format. This tool is deliberately
small: it reassembles ACL fragments per connection handle and prints ATT
write/notification payloads with timestamps. It does not need Wireshark.

Usage:
    python scripts/parse_btsnoop.py capture.btsnoop
    python scripts/parse_btsnoop.py capture.btsnoop --jsonl out.jsonl
    python scripts/parse_btsnoop.py capture.btsnoop --opcode 0x52 --opcode 0x1b
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from datetime import UTC, datetime

BTSNOOP_MAGIC = b"btsnoop\x00"
YEAR_ZERO_TO_UNIX = 62167219200  # seconds

ATT_NAMES = {
    0x01: "ERROR_RSP",
    0x02: "MTU_REQ",
    0x03: "MTU_RSP",
    0x04: "FIND_INFO_REQ",
    0x05: "FIND_INFO_RSP",
    0x06: "FIND_BY_TYPE_VALUE_REQ",
    0x07: "FIND_BY_TYPE_VALUE_RSP",
    0x08: "READ_BY_TYPE_REQ",
    0x09: "READ_BY_TYPE_RSP",
    0x0A: "READ_REQ",
    0x0B: "READ_RSP",
    0x0C: "READ_BLOB_REQ",
    0x0D: "READ_BLOB_RSP",
    0x0E: "READ_MULTIPLE_REQ",
    0x0F: "READ_MULTIPLE_RSP",
    0x10: "READ_BY_GROUP_REQ",
    0x11: "READ_BY_GROUP_RSP",
    0x12: "WRITE_REQ",
    0x13: "WRITE_RSP",
    0x16: "PREPARE_WRITE_REQ",
    0x17: "PREPARE_WRITE_RSP",
    0x18: "EXECUTE_WRITE_REQ",
    0x19: "EXECUTE_WRITE_RSP",
    0x1B: "NOTIFY",
    0x1D: "INDICATE",
    0x1E: "CONFIRM",
    0x52: "WRITE_CMD",
}

DIRECTIONS = {0: "host->ctrl", 1: "ctrl->host"}


def parse_btsnoop(path: str):
    with open(path, "rb") as fh:
        header = fh.read(16)
        if len(header) < 16 or not header.startswith(BTSNOOP_MAGIC):
            raise SystemExit("not a btsnoop file")
        _version, datalink = struct.unpack(">II", header[8:16])
        index = 0
        while True:
            rec = fh.read(24)
            if len(rec) < 24:
                break
            _orig_len, incl_len, flags, _drops, ts_us = struct.unpack(">IIIIQ", rec)
            data = fh.read(incl_len)
            if len(data) < incl_len:
                break
            index += 1
            ts = ts_us / 1_000_000 - YEAR_ZERO_TO_UNIX
            yield {
                "index": index,
                "ts": ts,
                "direction": DIRECTIONS.get(flags & 1, f"flags={flags}"),
                "datalink": datalink,
                "data": data,
            }


class AclReassembler:
    def __init__(self):
        self.buffers: dict[int, bytearray] = {}

    def feed(self, h4_type: int, data: bytes) -> list[tuple[int, bytes]]:
        if h4_type != 0x02 or len(data) < 4:
            return []
        handle_flags = int.from_bytes(data[0:2], "little")
        handle = handle_flags & 0x0FFF
        pb = (handle_flags >> 4) & 0x3
        length = int.from_bytes(data[2:4], "little")
        payload = data[4 : 4 + length]
        if pb == 0:
            self.buffers[handle] = bytearray(payload)
        elif pb == 1:
            self.buffers.setdefault(handle, bytearray()).extend(payload)
        else:
            return []
        buf = self.buffers.get(handle, bytearray())
        if len(buf) < 4:
            return []
        l2cap_len = int.from_bytes(buf[0:2], "little")
        cid = int.from_bytes(buf[2:4], "little")
        if len(buf) < 4 + l2cap_len:
            return []
        packet = bytes(buf[4 : 4 + l2cap_len])
        del self.buffers[handle]
        if cid == 0x0004:
            return [(handle, packet)]
        return []


def decode_att(data: bytes) -> dict | None:
    if not data:
        return None
    opcode = data[0]
    out = {"opcode": opcode, "name": ATT_NAMES.get(opcode, f"0x{opcode:02x}")}
    if opcode in (0x12, 0x52, 0x1B, 0x1D) and len(data) >= 3 or opcode in (0x0A, 0x0B, 0x0C, 0x0D) and len(data) >= 3:
        out["handle"] = int.from_bytes(data[1:3], "little")
        out["value_hex"] = data[3:].hex()
    elif opcode in (0x08, 0x09, 0x10, 0x11) and len(data) >= 5:
        out["start"] = int.from_bytes(data[1:3], "little")
        out["end"] = int.from_bytes(data[3:5], "little")
        out["value_hex"] = data[5:].hex()
    else:
        out["value_hex"] = data[1:].hex()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path")
    ap.add_argument("--jsonl", help="write decoded ATT records to JSONL")
    ap.add_argument("--handle", type=lambda s: int(s, 0), help="only this ATT handle")
    ap.add_argument("--opcode", action="append", type=lambda s: int(s, 0), help="only these ATT opcodes")
    args = ap.parse_args()

    h4 = AclReassembler()
    out = open(args.jsonl, "w", encoding="utf-8") if args.jsonl else None  # noqa: SIM115
    count = 0
    try:
        for record in parse_btsnoop(args.path):
            data = record["data"]
            if record["datalink"] == 1002:
                h4_type, payload = data[0], data[1:]
            else:
                h4_type, payload = 0x02, data
            for handle, l2cap in h4.feed(h4_type, payload):
                att = decode_att(l2cap)
                if not att:
                    continue
                if args.handle is not None and att.get("handle") != args.handle:
                    continue
                if args.opcode and att["opcode"] not in args.opcode:
                    continue
                count += 1
                iso = datetime.fromtimestamp(record["ts"], tz=UTC).isoformat(timespec="milliseconds")
                line = {
                    "index": record["index"],
                    "ts": record["ts"],
                    "iso": iso,
                    "direction": record["direction"],
                    "handle": handle,
                    **att,
                }
                if out:
                    out.write(json.dumps(line, sort_keys=True) + "\n")
                else:
                    handle_text = f"handle=0x{att['handle']:03x} " if "handle" in att else ""
                    print(
                        f"{iso} {record['direction']:12s} h=0x{handle:03x} "
                        f"{att['name']:14s} {handle_text}{att.get('value_hex','')}"
                    )
    finally:
        if out:
            out.close()
    print(f"\n{count} ATT records", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
