#!/usr/bin/env python3
"""Inspect a Huawei HOTA firmware container read-only.

Examples::

    python scripts/inspect_hota.py /tmp/opencode/ota/package.bin.apk
    python scripts/inspect_hota.py package.bin.apk --extract /tmp/hota
    python scripts/inspect_hota.py package.bin.apk --json > manifest.json

The parser never touches a device. Firmware packages can be large and are not
committed to the repository.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fitness_band.hota import (
    HotaError,
    extract,
    parse_hota,
    verify_entries,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("package", type=Path, help="HOTA .bin.apk container")
    ap.add_argument(
        "--extract",
        type=Path,
        metavar="DIR",
        help="write every component under DIR (SHA-256 verified)",
    )
    ap.add_argument("--json", action="store_true", help="emit manifest as JSON")
    ap.add_argument("--no-verify", action="store_true", help="skip SHA-256 verification")
    args = ap.parse_args(argv)

    data = args.package.read_bytes()

    try:
        pkg = parse_hota(data)
    except HotaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    verified: list[bool] | None = None
    if not args.no_verify:
        verified = verify_entries(data, pkg)

    if args.json:
        print(
            json.dumps(
                {
                    "tag": pkg.tag,
                    "version": pkg.version,
                    "build_time": pkg.build_time,
                    "signature_offset": pkg.signature_offset,
                    "signature_length": len(pkg.signature),
                    "data_offset": pkg.data_offset,
                    "components": [
                        {
                            "name": e.name,
                            "version": e.version,
                            "size": e.size,
                            "crc32": f"{e.crc32:08x}",
                            "sha256": e.sha256,
                            "source_digest": e.source_digest,
                            "offset": e.data_offset,
                            "verified": e.verified,
                        }
                        for e in pkg.entries
                    ],
                },
                indent=2,
            )
        )
    else:
        print(f"file             {args.package} ({len(data)} bytes)")
        print(f"tag              {pkg.tag}")
        print(f"version          {pkg.version}")
        print(f"build time       {pkg.build_time}")
        print(f"signature        {len(pkg.signature)} bytes at 0x{pkg.signature_offset:x}")
        print(f"payload          starts at 0x{pkg.data_offset:x}")
        print()
        print(f"{'#':>2}  {'size':>9}  {'sha256':>12}  name")
        for i, e in enumerate(pkg.entries):
            mark = ""
            if e.verified is True:
                mark = "ok"
            elif e.verified is False:
                mark = "BAD"
            print(f"{i:2d}  {e.size:9d}  {e.sha256[:12]:>12}  {e.name}  {mark}".rstrip())

    if verified is not None and not all(verified):
        bad = [e.name for e in pkg.entries if e.verified is False]
        print(f"verification failed: {', '.join(bad)}", file=sys.stderr)
        return 2

    if args.extract:
        try:
            written = extract(data, pkg, args.extract)
        except HotaError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"extracted {len(written)} component(s) to {args.extract}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
