"""File-based control channel between the web UI and the acquisition daemon.

The daemon polls a small JSON file. This keeps the acquisition process alive
and independent when the web interface is down, and avoids a socket permission
surface. Writes are atomic (temp file + replace).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class ControlState:
    paused: bool = False
    force_reconnect: int = 0
    reset_adapter: int = 0
    updated_at: float = 0.0


def read_control(path: str | Path) -> ControlState:
    target = Path(path)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return ControlState()
    return ControlState(
        paused=bool(raw.get("paused", False)),
        force_reconnect=int(raw.get("force_reconnect", 0)),
        reset_adapter=int(raw.get("reset_adapter", 0)),
        updated_at=float(raw.get("updated_at", 0.0)),
    )


def write_control(path: str | Path, state: ControlState) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    state.updated_at = time.time()
    tmp = target.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(asdict(state), handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, target)


def apply_action(path: str | Path, action: str) -> ControlState:
    """Apply a dashboard action and persist the new control state."""

    state = read_control(path)
    if action == "start":
        state.paused = False
        state.force_reconnect += 1
    elif action == "stop":
        state.paused = True
    elif action == "connect":
        state.paused = False
        state.force_reconnect += 1
    elif action == "disconnect":
        state.paused = True
    elif action == "reconnect":
        state.paused = False
        state.force_reconnect += 1
    elif action == "reset_adapter":
        state.reset_adapter += 1
    else:
        raise ValueError(f"unknown control action: {action}")
    write_control(path, state)
    return state


__all__ = ["ControlState", "apply_action", "read_control", "write_control"]
