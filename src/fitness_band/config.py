"""Runtime configuration.

Addresses are never committed. Set ``BAND9_ADDRESS`` locally or pass
``--address`` on the command line.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default)).expanduser()


@dataclass
class Settings:
    address: str | None = os.environ.get("BAND9_ADDRESS") or None
    endpoint: str = os.environ.get("BAND9_ENDPOINT", "hr_broadcast")
    data_dir: Path = field(default_factory=lambda: _env_path("BAND9_DATA_DIR", "data"))
    captures_dir: Path = field(default_factory=lambda: _env_path("BAND9_CAPTURES_DIR", "captures"))
    db_path: Path | None = None
    scan_timeout: float = float(os.environ.get("BAND9_SCAN_TIMEOUT", "15"))
    connect_timeout: float = float(os.environ.get("BAND9_CONNECT_TIMEOUT", "30"))
    reconnect: bool = os.environ.get("BAND9_RECONNECT", "1") not in {"0", "false", "no"}

    def __post_init__(self) -> None:
        if self.db_path is None:
            self.db_path = self.data_dir / "band9.sqlite3"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.captures_dir.mkdir(parents=True, exist_ok=True)
        (self.captures_dir / "raw").mkdir(parents=True, exist_ok=True)
        (self.captures_dir / "gatt").mkdir(parents=True, exist_ok=True)
