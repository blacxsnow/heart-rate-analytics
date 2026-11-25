#!/usr/bin/env python3
"""Match Frida GATT ciphertexts to the app's `Cipher.doFinal` events.

Inputs:
  * GATT log from scripts/frida_ble_hooks.js
  * Optional crypto log from scripts/frida_crypto_hooks.js

The crypto log is used only to recover plaintext; keys are never printed or
written. Output is a sanitised timeline suitable for protocol analysis.

Usage:
  python scripts/analyze_frida_capture.py \
      --gatt captures/android/frida_gatt.log \
      --crypto captures/android/frida_crypto.log \
      --out /tmp/opencode/android/timeline.txt
"""

from __future__ import annotations

import argparse
import ast
import collections
import re
from pathlib import Path

from fitness_band.protocol import TLV, FrameDecoder


def read_messages(path: Path) -> list[dict]:
    messages: list[dict] = []
    for line in path.read_text(errors="replace").splitlines():
        match = re.search(r"message: (\{.*?\}) data:", line)
        if not match:
            continue
        try:
            record = ast.literal_eval(match.group(1))
        except (ValueError, SyntaxError):
            continue
        payload = record.get("payload") if isinstance(record, dict) else None
        if isinstance(payload, dict) and "kind" in payload:
            messages.append(payload)
    return messages


def parse_tlvs(hexstr: str | None) -> list[tuple[str, str]]:
    if not hexstr:
        return []
    try:
        return [(f"0x{tlv.tag:02x}", tlv.value.hex()) for tlv in TLV.parse_all(bytes.fromhex(hexstr))]
    except (ValueError, TypeError):
        return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gatt", required=True, type=Path)
    ap.add_argument("--crypto", type=Path, help="crypto log (optional)")
    ap.add_argument("--out", type=Path, help="write timeline here")
    ap.add_argument("--reveal-personal", action="store_true", help="do not apply example redaction")
    args = ap.parse_args()

    gatt = read_messages(args.gatt)
    crypto = read_messages(args.crypto) if args.crypto else []

    encrypt_by_output: dict[str, list[dict]] = collections.defaultdict(list)
    decrypt_by_input: dict[str, list[dict]] = collections.defaultdict(list)
    for record in crypto:
        if record.get("kind") != "Cipher.doFinal":
            continue
        if record.get("output_hex"):
            encrypt_by_output[record["output_hex"]].append(record)
        if record.get("input_hex"):
            decrypt_by_input[record["input_hex"]].append(record)

    lines: list[str] = []
    unique: dict[tuple[str, int, int], dict] = collections.OrderedDict()
    seen: set[tuple[str, str]] = set()

    for record in gatt:
        kind = record.get("kind")
        if kind not in ("gatt.writeCharacteristic", "callback.onCharacteristicChanged"):
            continue
        raw_hex = record.get("value")
        if not raw_hex:
            continue
        direction = "tx" if kind == "gatt.writeCharacteristic" else "rx"
        if (direction, raw_hex) in seen:
            continue
        seen.add((direction, raw_hex))
        try:
            frames = list(FrameDecoder().feed(bytes.fromhex(raw_hex)))
        except ValueError:
            continue
        for frame in frames:
            if frame.slice_type != 0:
                lines.append(f"{record.get('t')} {direction} SLICE {frame.slice_type}")
                continue
            try:
                values = {tlv.tag: tlv.value for tlv in frame.tlvs}
            except ValueError:
                continue
            plaintext: bytes | None = None
            if 0x7D in values and 0x7E in values:
                ciphertext = values[0x7E].hex()
                events = encrypt_by_output.get(ciphertext) if direction == "tx" else decrypt_by_input.get(ciphertext)
                if events:
                    event = events[0]
                    text = event.get("input_hex") if direction == "tx" else event.get("output_hex")
                    plaintext = bytes.fromhex(text) if text else None
            else:
                plaintext = frame.payload[2:]

            line = (
                f"{record.get('t')} {direction} svc=0x{frame.service_id:02x} "
                f"cmd=0x{frame.command_id:02x} pt={plaintext.hex() if plaintext else ''}"
            )
            lines.append(line)
            if plaintext is not None:
                entry = unique.setdefault(
                    (direction, frame.service_id, frame.command_id),
                    {"n": 0, "examples": []},
                )
                entry["n"] += 1
                if len(entry["examples"]) < 5:
                    entry["examples"].append(plaintext.hex())

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Unique commands:")
    for (direction, service, command), entry in unique.items():
        examples = entry["examples"] if args.reveal_personal else [e[:64] for e in entry["examples"]]
        print(
            f"  {direction} 0x{service:02x}/0x{command:02x} "
            f"n={entry['n']} examples={examples}"
        )
    print(f"\n{len(lines)} frames; write with --out for the full timeline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
