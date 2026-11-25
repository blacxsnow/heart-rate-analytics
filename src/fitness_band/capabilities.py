"""Load and validate the machine-readable acquisition capability matrix."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REALTIME_VALUES = {"yes", "no", "partial", "unknown"}
VERIFICATION_VALUES = {"confirmed", "partial", "hypothesis", "unknown"}

REQUIRED_FIELDS = {
    "id",
    "measurement",
    "realtime",
    "historical",
    "sampling_hz",
    "resolution_bits",
    "timestamp_precision",
    "access",
    "dependencies",
    "verification",
    "evidence",
}

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "capabilities" / "matrix.yaml"


class CapabilityError(ValueError):
    """Raised when the capability matrix is malformed."""


@dataclass(frozen=True)
class Capability:
    id: str
    measurement: str
    realtime: str
    historical: str
    sampling_hz: float | None
    resolution_bits: int | None
    timestamp_precision: str | None
    access: str
    dependencies: tuple[str, ...]
    verification: str
    evidence: tuple[str, ...]
    notes: str = ""

    @property
    def is_usable_realtime(self) -> bool:
        return self.realtime == "yes" and self.verification == "confirmed"


def _optional_number(value: Any, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CapabilityError(f"{field} must be a number or null")
    return value


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise CapabilityError(f"{field} must be a list of strings")
    return tuple(value)


def parse_matrix(document: Any) -> dict[str, Capability]:
    if not isinstance(document, dict):
        raise CapabilityError("matrix root must be a mapping")
    if document.get("schema_version") != 1:
        raise CapabilityError("unsupported schema_version")

    entries = document.get("entries")
    if not isinstance(entries, list) or not entries:
        raise CapabilityError("entries must be a non-empty list")

    out: dict[str, Capability] = {}
    for index, raw in enumerate(entries):
        if not isinstance(raw, dict):
            raise CapabilityError(f"entry {index} must be a mapping")
        missing = REQUIRED_FIELDS - raw.keys()
        if missing:
            raise CapabilityError(f"entry {index} missing {sorted(missing)}")

        entry_id = raw["id"]
        if not isinstance(entry_id, str) or not entry_id:
            raise CapabilityError(f"entry {index} has invalid id")
        if entry_id in out:
            raise CapabilityError(f"duplicate entry id {entry_id}")

        for field in ("realtime", "historical"):
            if raw[field] not in REALTIME_VALUES:
                raise CapabilityError(f"{entry_id}: invalid {field} {raw[field]!r}")
        if raw["verification"] not in VERIFICATION_VALUES:
            raise CapabilityError(f"{entry_id}: invalid verification {raw['verification']!r}")

        resolution = raw["resolution_bits"]
        if resolution is not None and (
            isinstance(resolution, bool) or not isinstance(resolution, int)
        ):
            raise CapabilityError(f"{entry_id}: resolution_bits must be int or null")

        out[entry_id] = Capability(
            id=entry_id,
            measurement=str(raw["measurement"]),
            realtime=raw["realtime"],
            historical=raw["historical"],
            sampling_hz=_optional_number(raw["sampling_hz"], "sampling_hz"),
            resolution_bits=resolution,
            timestamp_precision=raw["timestamp_precision"],
            access=str(raw["access"]),
            dependencies=_string_tuple(raw["dependencies"], "dependencies"),
            verification=raw["verification"],
            evidence=_string_tuple(raw["evidence"], "evidence"),
            notes=str(raw.get("notes", "")).strip(),
        )
    return out


def load_matrix(path: str | Path | None = None) -> dict[str, Capability]:
    """Load the matrix from ``path`` (defaults to ``capabilities/matrix.yaml``)."""

    target = Path(path) if path is not None else DEFAULT_PATH
    try:
        document = yaml.safe_load(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CapabilityError(f"matrix not found: {target}") from exc
    except yaml.YAMLError as exc:
        raise CapabilityError(f"invalid YAML: {exc}") from exc
    return parse_matrix(document)


__all__ = [
    "DEFAULT_PATH",
    "Capability",
    "CapabilityError",
    "load_matrix",
    "parse_matrix",
]
