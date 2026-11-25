"""Acquisition daemon entry point (systemd friendly, no terminal required)."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

from ..database import AcquisitionDB
from .collector import BandHRCollector, CollectorConfig
from .simulation import SimulatedCollector
from .spool import SpoolQueue
from .state import StateWriter, read_state

LOG = logging.getLogger("band9.acquisition")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def default_data_dir() -> Path:
    return Path(os.environ.get("BAND9_DATA_DIR", str(Path.home() / ".local" / "share" / "band9")))


def build_parser() -> argparse.ArgumentParser:
    data = default_data_dir()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=data / "acquisition.sqlite3")
    parser.add_argument("--state", type=Path, default=data / "state.json")
    parser.add_argument("--control", type=Path, default=data / "control.json")
    parser.add_argument("--spool", type=Path, default=data / "spool")
    parser.add_argument("--address", help="optional fixed BLE address")
    parser.add_argument("--scan-timeout", type=float, default=12.0)
    parser.add_argument("--connect-timeout", type=float, default=30.0)
    parser.add_argument("--stale-timeout", type=float, default=15.0)
    parser.add_argument("--expected-interval", type=float, default=1.0)
    parser.add_argument("--backoff-initial", type=float, default=2.0)
    parser.add_argument("--backoff-max", type=float, default=60.0)
    parser.add_argument("--simulate", action="store_true", help="synthetic data (development only)")
    parser.add_argument("--duration", type=float, help="stop after N seconds (testing)")
    parser.add_argument("--log-level", default="INFO")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    for handler in logging.getLogger().handlers:
        handler.setFormatter(JsonFormatter())

    args.db.parent.mkdir(parents=True, exist_ok=True)
    db = AcquisitionDB(args.db)
    recovered = db.recover_open_sessions()
    db.add_event(
        "process_start",
        details={
            "pid": os.getpid(),
            "simulate": bool(args.simulate),
            "recovered_sessions": recovered,
        },
    )
    previous_state = read_state(args.state)
    state = StateWriter(args.state, min_interval=0.4)
    state.update(
        force=True,
        service_status="starting",
        connection_status="disconnected",
        adapter_available=None,
        started_at=time.time(),
        device_id=args.address or previous_state.get("device_id"),
    )
    spool = SpoolQueue(args.spool)

    if args.simulate:
        collector = SimulatedCollector(
            db=db,
            state=state,
            spool=spool,
            control_path=str(args.control),
            interval=args.expected_interval,
        )
        LOG.warning("SIMULATION MODE: records are source='simulated'")
    else:
        collector = BandHRCollector(
            db=db,
            state=state,
            spool=spool,
            control_path=args.control,
            config=CollectorConfig(
                address=args.address,
                scan_timeout=args.scan_timeout,
                connect_timeout=args.connect_timeout,
                stale_timeout=args.stale_timeout,
                expected_interval=args.expected_interval,
                backoff_initial=args.backoff_initial,
                backoff_max=args.backoff_max,
            ),
        )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def request_stop(*_args: object) -> None:
        LOG.info("stop requested")
        collector.stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, request_stop)

    async def runner() -> None:
        if args.simulate:
            await collector.run(duration=args.duration)
        elif args.duration:
            task = asyncio.create_task(collector.run())
            await asyncio.sleep(args.duration)
            collector.stop()
            await task
        else:
            await collector.run()

    try:
        loop.run_until_complete(runner())
    finally:
        db.add_event("process_stop", details={"pid": os.getpid()})
        state.update(force=True, service_status="stopped", connection_status="stopped")
        db.close()
        loop.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
