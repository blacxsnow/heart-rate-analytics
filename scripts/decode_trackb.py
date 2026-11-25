#!/usr/bin/env python3
"""Decode a Track B Frida log into reassembled, decrypted FE86 frames.

Input is the line-oriented output of ``scripts/frida_trackb_capture.js``.
The per-session AES-GCM key is supplied on the command line; it is never
stored in the repository.

Example::

    python scripts/decode_trackb.py capture.log --key <64-hex> \
        --jsonl decoded.jsonl --summary

Only the ``gatt.write`` / ``gatt.notifyRx`` records with a value are used.
Consecutive duplicate writes are collapsed (the capture hooks can see the same
GATT write twice).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fitness_band.protocol import TLV, FrameDecoder, ProtocolError

RECORD_RE = re.compile(r"\{'type': 'send', 'payload': (\{.*\})\} data:")
FE_WRITE = "0000fe01-0000-1000-8000-00805f9b34fb"
FE_NOTIFY = "0000fe02-0000-1000-8000-00805f9b34fb"


def parse_log(path: Path) -> list[dict]:
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = RECORD_RE.search(line)
        if not match:
            continue
        try:
            records.append(ast.literal_eval(match.group(1)))
        except (ValueError, SyntaxError):
            continue
    return records


def reassemble(records: list[dict], kind: str, uuid: str) -> list[tuple[float, object]]:
    decoder = FrameDecoder()
    frames: list[tuple[float, object]] = []
    last_value: str | None = None
    for record in records:
        if record.get("kind") != kind or record.get("uuid") != uuid:
            continue
        value = record.get("value")
        if not value or value == last_value:
            continue
        last_value = value
        try:
            decoded = decoder.feed(bytes.fromhex(value))
        except (ValueError, ProtocolError):
            continue
        frames.extend((float(record["t"]), frame) for frame in decoded)
    return frames


def decrypt(frame, keys: list[bytes]) -> tuple[bytes | None, bool]:
    """Return (plaintext_tlv_block, was_encrypted)."""

    values = {tlv.tag: tlv.value for tlv in frame.tlvs}
    if 0x7E not in values:
        return frame.payload[2:], False
    if 0x7D not in values:
        return None, True

    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    for key in keys:
        try:
            return AESGCM(key).decrypt(values[0x7D], values[0x7E], None), True
        except InvalidTag:
            continue
    return None, True


def describe(t: float, direction: str, frame, keys: list[bytes]) -> dict:
    plain, encrypted = decrypt(frame, keys)
    entry = {
        "t": t,
        "dir": direction,
        "service": frame.service_id,
        "command": frame.command_id,
        "encrypted": encrypted,
        "plaintext_hex": plain.hex() if plain is not None else None,
        "tlvs": [],
    }
    if plain:
        try:
            tlvs = TLV.parse_all(plain)
        except ProtocolError:
            tlvs = []
        entry["tlvs"] = [{"tag": tlv.tag, "value_hex": tlv.value.hex()} for tlv in tlvs]
        if frame.service_id == 0x01 and frame.command_id == 0x28:
            for tlv in tlvs:
                if tlv.tag == 0x01:
                    text = tlv.value.rstrip(b"\x00").decode("utf-8", "replace")
                    try:
                        entry["json"] = json.loads(text)
                    except json.JSONDecodeError:
                        entry["text"] = text
                    break
    return entry


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("log", type=Path)
    ap.add_argument("--key", action="append", default=[], help="per-session key, hex")
    ap.add_argument("--jsonl", type=Path, help="write decoded frames as JSONL")
    ap.add_argument("--summary", action="store_true", help="print one line per frame")
    args = ap.parse_args(argv)

    try:
        keys = [bytes.fromhex(k) for k in args.key]
    except ValueError as exc:
        print(f"error: bad key: {exc}", file=sys.stderr)
        return 2

    records = parse_log(args.log)
    out = []
    for kind, uuid, direction in (
        ("gatt.write", FE_WRITE, "tx"),
        ("gatt.notifyRx", FE_NOTIFY, "rx"),
    ):
        for t, frame in reassemble(records, kind, uuid):
            out.append(describe(t, direction, frame, keys))

    out.sort(key=lambda item: item["t"])

    if args.summary:
        for item in out:
            text = ""
            if item.get("json"):
                text = f" message={item['json'].get('message')}"
            elif item["plaintext_hex"]:
                raw = bytes.fromhex(item["plaintext_hex"])
                try:
                    text = " " + raw.decode("ascii")
                except UnicodeDecodeError:
                    text = " " + item["plaintext_hex"][:80]
            print(
                f"{item['t']:8.2f} {item['dir']} "
                f"{item['service']:02x}/{item['command']:02x}"
                f"{' enc' if item['encrypted'] else '    '}{text[:120]}"
            )

    if args.jsonl:
        with args.jsonl.open("w", encoding="utf-8") as handle:
            for item in out:
                handle.write(json.dumps(item, sort_keys=True) + "\n")

    print(f"{len(out)} frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
