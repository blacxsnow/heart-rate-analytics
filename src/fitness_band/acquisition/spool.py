"""Disk-backed spool for observations that could not be written immediately.

The daemon writes through this queue only when the SQLite insert raises. The
spool is drained at startup and periodically; records are JSON objects with the
same keyword arguments accepted by ``AcquisitionDB.add_measurement``.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any


class SpoolQueue:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _files(self) -> list[Path]:
        return sorted(self.directory.glob("pending-*.jsonl"))

    def pending_count(self) -> int:
        count = 0
        for path in self._files():
            try:
                count += sum(
                    1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
                )
            except OSError:
                continue
        return count

    def enqueue(self, record: dict[str, Any]) -> Path:
        day = record.get("received_at_utc", "")[:10] or "unknown"
        path = self.directory / f"pending-{day}.jsonl"
        line = json.dumps(record, sort_keys=True, default=str)
        with self._lock, path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return path

    def drain(self, insert: Callable[[dict[str, Any]], Any], *, limit: int = 10000) -> int:
        """Try to insert spooled records; stop on the first failure.

        A partially drained file is atomically rewritten with the remaining
        lines, so a crash during draining does not lose records.
        """

        written = 0
        for path in self._files():
            if written >= limit:
                break
            try:
                lines = [
                    line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
                ]
            except OSError:
                continue
            remaining: list[str] = []
            for index, line in enumerate(lines):
                if written >= limit:
                    remaining.extend(lines[index:])
                    break
                try:
                    record = json.loads(line)
                    insert(record)
                    written += 1
                except Exception:  # noqa: BLE001 - keep the record for the next drain
                    remaining.extend(lines[index:])
                    break
            if remaining:
                tmp = path.with_suffix(".tmp")
                tmp.write_text("\n".join(remaining) + "\n", encoding="utf-8")
                os.replace(tmp, path)
            else:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
        return written


__all__ = ["SpoolQueue"]
