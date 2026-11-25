"""Canonical runtime paths shared by the daemon and web applications."""

from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("BAND9_DATA_DIR", str(Path.home() / ".local" / "share" / "band9")))


def db_path() -> Path:
    return Path(os.environ.get("BAND9_DB", str(data_dir() / "acquisition.sqlite3")))


def state_path() -> Path:
    return Path(os.environ.get("BAND9_STATE", str(data_dir() / "state.json")))


def control_path() -> Path:
    return Path(os.environ.get("BAND9_CONTROL", str(data_dir() / "control.json")))


def spool_dir() -> Path:
    return Path(os.environ.get("BAND9_SPOOL", str(data_dir() / "spool")))


__all__ = ["control_path", "data_dir", "db_path", "spool_dir", "state_path"]
