"""CLI entry point: ``python -m fitness_band`` or the ``band9`` script."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from rich.console import Console
from rich.table import Table

from . import uuids
from .authentication import probe_link_params
from .ble_scanner import find_endpoint, scan
from .config import Settings
from .gatt_inspector import GattReport, format_summary, inspect_gatt
from .heart_rate import HeartRateMonitor
from .storage import SQLiteStore, iso_utc

console = Console()


def _print_json(data: object) -> None:
    console.print_json(json.dumps(data, default=str))


def _choose_address(address: str | None, settings: Settings, endpoint: str) -> str:
    address = address or settings.address
    if address:
        return address
    adv = asyncio.run(find_endpoint(endpoint=endpoint, timeout=settings.scan_timeout))
    if adv is None:
        raise SystemExit(
            f"No Band 9 endpoint ({endpoint}) found. Start HR Data Broadcast on the band, "
            "or pass --address."
        )
    return adv.address


def _write_json(path: str | Path, data: object) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path


# --- commands --------------------------------------------------------------
def cmd_scan(args: argparse.Namespace) -> int:
    results = asyncio.run(
        scan(
            args.duration,
            name_contains=args.name,
            address=args.address,
            service_uuid=args.service,
        )
    )
    table = Table(title=f"BLE scan ({args.duration:.0f}s)")
    table.add_column("Address")
    table.add_column("RSSI", justify="right")
    table.add_column("Endpoint")
    table.add_column("Name")
    table.add_column("Services")
    for item in results:
        if not args.all and not (item.is_hr_broadcast or item.is_normal_endpoint):
            continue
        table.add_row(
            item.address,
            str(item.rssi),
            item.endpoint,
            item.name or "",
            ",".join(s.split("-")[0] for s in item.service_uuids[:4]),
        )
    console.print(table)
    if args.json:
        path = _write_json(args.json, [item.to_dict() for item in results])
        console.print(f"Wrote {path}")
    return 0


def cmd_endpoints(args: argparse.Namespace) -> int:
    results = asyncio.run(scan(args.duration))
    bands = [item for item in results if item.is_hr_broadcast or item.is_normal_endpoint]
    if not bands:
        console.print("[yellow]No Huawei Band 9 endpoint found.[/yellow]")
        return 1
    for item in bands:
        console.print(
            f"[bold]{item.endpoint:12s}[/bold] {item.address}  RSSI {item.rssi:4d}  {item.name}"
        )
    return 0


def cmd_gatt(args: argparse.Namespace) -> int:
    settings = Settings()
    address = _choose_address(args.address, settings, args.endpoint)
    notify_uuids = set(args.notify or [])
    if not notify_uuids:
        notify_uuids = {uuids.HEART_RATE_MEASUREMENT}
    report: GattReport = asyncio.run(
        inspect_gatt(
            address,
            read_safe=not args.no_read,
            subscribe_seconds=args.subscribe,
            notify_uuids=notify_uuids,
            subscribe_all_notify=args.all_notify,
            timeout=args.timeout,
        )
    )
    console.print(format_summary(report))
    if report.reads:
        console.print("\n[bold]Safe reads[/bold]")
        for uuid, entry in report.reads.items():
            if entry.get("ok"):
                console.print(
                    f"  {uuid}  {entry['name'] or ''}: {entry['value_hex']}"
                    + (f"  {entry['value_text']!r}" if entry.get("value_text") else "")
                )
            else:
                console.print(f"  {uuid}  [red]FAILED[/red] {entry.get('error')}")
    if report.notifications:
        console.print(f"\n[bold]Notifications ({len(report.notifications)})[/bold]")
        for note in report.notifications[-20:]:
            console.print(f"  {note.iso} {note.characteristic} {note.data_hex}")
    out = args.out or str(Path("captures/gatt") / f"gatt_{address.replace(':', '').lower()}.json")
    path = _write_json(out, report.to_dict())
    console.print(f"\nWrote {path}")
    return 0


def cmd_hr(args: argparse.Namespace) -> int:
    settings = Settings(address=args.address or Settings().address)
    settings.ensure_dirs()
    store = SQLiteStore(args.db or settings.db_path)
    jsonl = args.jsonl or (settings.captures_dir / "raw" / f"hr_{int(time.time())}.jsonl")

    last_print = 0.0

    def on_measurement(measurement, ts: float) -> None:
        nonlocal last_print
        now = time.monotonic()
        if args.quiet or now - last_print < 1.0:
            return
        last_print = now
        contact = "?" if measurement.sensor_contact is None else ("yes" if measurement.sensor_contact else "no")
        console.print(
            f"{iso_utc(ts)}  [bold]{measurement.heart_rate_bpm:3d}[/bold] bpm  "
            f"contact={contact}  raw={measurement.flags:02x}"
        )

    def on_status(state: str, extra: dict) -> None:
        if args.quiet:
            return
        if state == "connected":
            console.print(f"[green]connected[/green] {extra.get('address')} session={extra.get('session_id')}")
        elif state == "disconnected":
            console.print("[yellow]disconnected[/yellow]")
        elif state in {"error", "scan_miss"}:
            console.print(f"[red]{state}[/red] {extra}")

    monitor = HeartRateMonitor(
        store=store,
        address=settings.address,
        scan_timeout=settings.scan_timeout,
        connect_timeout=settings.connect_timeout,
        reconnect=not args.no_reconnect,
        jsonl_path=jsonl,
        on_measurement=on_measurement,
        on_status=on_status,
    )
    console.print(
        "Acquiring standard HRS. Keep HR Data Broadcast active on the band. Ctrl+C to stop."
    )
    try:
        stats = asyncio.run(monitor.run(args.duration))
    except KeyboardInterrupt:
        monitor.stop()
        stats = monitor.stats
    finally:
        store.close()

    span = (stats.ended_at or time.time()) - stats.started_at
    console.print(
        f"\n[bold]Summary[/bold] packets={stats.packets} parse_errors={stats.parse_errors} "
        f"connections={stats.connections} span={span:.1f}s "
        f"mean_rate={stats.packets / span if span else 0:.2f} Hz"
    )
    console.print(f"Raw JSONL: {jsonl}")
    console.print(f"SQLite: {settings.db_path if not args.db else args.db}")
    return 0 if stats.packets else 2


def cmd_probe_link(args: argparse.Namespace) -> int:
    if not args.yes:
        console.print(
            "[yellow]This sends the documented LinkParams handshake to FE01.[/yellow]\n"
            "It does not bond or change configuration. Re-run with --yes to confirm."
        )
        return 1
    settings = Settings()
    address = _choose_address(args.address, settings, "any")
    probe = asyncio.run(
        probe_link_params(
            address,
            timeout=args.timeout,
            connect_timeout=settings.connect_timeout,
            out_path=args.out,
        )
    )
    _print_json(probe.to_dict())
    if probe.link_params:
        console.print(
            f"\nAuth family: [bold]{probe.link_params.auth_family()}[/bold]  "
            f"authVersion={probe.link_params.auth_version}  bondState={probe.link_params.bond_state}"
        )
    return 0 if probe.link_params else 2


def cmd_summary(args: argparse.Namespace) -> int:
    store = SQLiteStore(args.db)
    try:
        summary = store.summary()
    finally:
        store.close()
    _print_json(summary)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    store = SQLiteStore(args.db)
    try:
        if args.csv:
            n = store.export_csv(args.csv, metric=args.metric)
            console.print(f"Wrote {n} rows to {args.csv}")
        if args.jsonl:
            n = store.export_jsonl(args.jsonl, metric=args.metric)
            console.print(f"Wrote {n} rows to {args.jsonl}")
    finally:
        store.close()
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    console.print(f"Python: {sys.version.split()[0]}")
    try:
        console.print(f"bleak: {version('bleak')}")
    except PackageNotFoundError:
        console.print("bleak: [red]not installed[/red]")
    settings = Settings()
    console.print(f"Saved address: {settings.address or '<none>'}")
    console.print("Scanning for Band 9 endpoints...")
    results = asyncio.run(scan(8.0))
    bands = [item for item in results if item.is_hr_broadcast or item.is_normal_endpoint]
    if not bands:
        console.print(
            "[yellow]No Band 9 found.[/yellow] Check: adapter powered, phone Bluetooth off, "
            "band awake, HR Data Broadcast started."
        )
        return 1
    for item in bands:
        console.print(f"  {item.endpoint:12s} {item.address}  RSSI {item.rssi:4d}  {item.name}")
    if any(item.is_hr_broadcast for item in bands):
        console.print("[green]Standard HRS endpoint is advertising.[/green]")
    else:
        console.print(
            "[yellow]HRS endpoint absent.[/yellow] On the band: Settings -> HR Data Broadcasts -> start."
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="band9",
        description="Independent BLE acquisition for the Huawei Band 9",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scan", help="scan BLE advertisements")
    p.add_argument("--duration", type=float, default=10)
    p.add_argument("--name", help="name substring filter")
    p.add_argument("--address", help="exact address filter")
    p.add_argument("--service", help="service UUID filter")
    p.add_argument("--all", action="store_true", help="show non-Huawei devices too")
    p.add_argument("--json", help="write JSON results")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("endpoints", help="show Band 9 endpoints only")
    p.add_argument("--duration", type=float, default=8)
    p.set_defaults(func=cmd_endpoints)

    p = sub.add_parser("gatt", help="enumerate GATT (read-only)")
    p.add_argument("--address")
    p.add_argument("--endpoint", default="hr_broadcast", choices=["hr_broadcast", "normal", "any"])
    p.add_argument("--no-read", action="store_true", help="skip safe reads")
    p.add_argument("--subscribe", type=float, default=0, help="seconds to capture notifications")
    p.add_argument("--notify", action="append", help="characteristic UUID to subscribe (repeatable)")
    p.add_argument("--all-notify", action="store_true", help="subscribe every notify characteristic")
    p.add_argument("--timeout", type=float, default=30)
    p.add_argument("--out", help="JSON output path")
    p.set_defaults(func=cmd_gatt)

    p = sub.add_parser("hr", help="continuous heart rate over standard HRS")
    p.add_argument("--address")
    p.add_argument("--duration", type=float, default=None, help="seconds (default: until stopped)")
    p.add_argument("--db", help="SQLite path")
    p.add_argument("--jsonl", help="raw JSONL path")
    p.add_argument("--no-reconnect", action="store_true")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_hr)

    p = sub.add_parser("probe-link", help="send read-only LinkParams handshake")
    p.add_argument("--address")
    p.add_argument("--timeout", type=float, default=10)
    p.add_argument("--out", default="captures/gatt/link_params.json")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_probe_link)

    p = sub.add_parser("summary", help="summarise the local database")
    p.add_argument("--db", default=str(Settings().db_path))
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("export", help="export measurements to CSV/JSONL")
    p.add_argument("--db", default=str(Settings().db_path))
    p.add_argument("--csv")
    p.add_argument("--jsonl")
    p.add_argument("--metric")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("doctor", help="check environment and discover endpoints")
    p.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
