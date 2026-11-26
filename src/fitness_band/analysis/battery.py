"""Charge-aware battery accounting.

Battery readings are point observations. Charging is a separate event with a
target percentage (and optional start percentage and duration), so a charge jump
never corrupts the discharge rate. Events live in ``device_events``; no schema
change is needed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

READING_EVENT = "battery_reading"
CHARGE_EVENT = "battery_charge"


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _details(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("details")
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _percent(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not 0 <= number <= 100:
        return None
    return number


def _public(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if key != "_at"}


def parse_battery_readings(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    readings: list[dict[str, Any]] = []
    for event in events:
        details = _details(event)
        percent = _percent(details.get("percent"))
        at = _parse_time(event.get("event_time_utc"))
        if percent is None or at is None:
            continue
        readings.append(
            {
                "event_id": event.get("event_id"),
                "recorded_at": at.isoformat(timespec="milliseconds"),
                "percent": percent,
                "note": details.get("note"),
                "_at": at,
            }
        )
    return sorted(readings, key=lambda item: item["_at"])


def parse_battery_charges(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    charges: list[dict[str, Any]] = []
    for event in events:
        details = _details(event)
        to_percent = _percent(details.get("to_percent"))
        at = _parse_time(event.get("event_time_utc"))
        if to_percent is None or at is None:
            continue
        from_percent = _percent(details.get("from_percent"))
        try:
            duration = (
                float(details["duration_minutes"])
                if details.get("duration_minutes") is not None
                else None
            )
        except (TypeError, ValueError):
            duration = None
        if duration is not None and duration < 0:
            duration = None
        rate_min = None
        if (
            from_percent is not None
            and duration is not None
            and duration > 0
            and to_percent >= from_percent
        ):
            rate_min = (to_percent - from_percent) / duration
        charges.append(
            {
                "event_id": event.get("event_id"),
                "recorded_at": at.isoformat(timespec="milliseconds"),
                "from_percent": from_percent,
                "to_percent": to_percent,
                "duration_minutes": duration,
                "charge_rate_percent_per_minute": (
                    round(rate_min, 4) if rate_min is not None else None
                ),
                "charge_rate_percent_per_hour": (
                    round(rate_min * 60.0, 4) if rate_min is not None else None
                ),
                "note": details.get("note"),
                "_at": at,
            }
        )
    return sorted(charges, key=lambda item: item["_at"])


def _drain_block(
    start_percent: float,
    start_at: datetime,
    end_percent: float,
    end_at: datetime,
    *,
    basis: str,
) -> dict[str, Any]:
    hours = (end_at - start_at).total_seconds() / 3600.0
    if hours <= 0:
        return {
            "available": False,
            "basis": basis,
            "reason": "start and end are not separated in time",
        }
    drain_per_hour = (start_percent - end_percent) / hours
    return {
        "available": True,
        "basis": basis,
        "start_percent": round(start_percent, 3),
        "start_at": start_at.isoformat(timespec="milliseconds"),
        "end_percent": round(end_percent, 3),
        "end_at": end_at.isoformat(timespec="milliseconds"),
        "hours": round(hours, 3),
        "drain_percent_per_hour": round(drain_per_hour, 4),
        "drain_percent_per_day": round(drain_per_hour * 24.0, 3),
    }


def battery_summary(
    readings: list[dict[str, Any]],
    charges: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the latest display value, charge rate and charge-aware drain."""
    now = (now or datetime.now(tz=UTC)).astimezone(UTC)
    readings = sorted(readings, key=lambda item: item["_at"])
    charges = sorted(charges, key=lambda item: item["_at"])
    latest_reading = readings[-1] if readings else None
    latest_charge = charges[-1] if charges else None
    warnings: list[str] = []

    display = None
    if latest_charge and (
        latest_reading is None or latest_charge["_at"] >= latest_reading["_at"]
    ):
        display = {
            "kind": "charge",
            "percent": latest_charge["to_percent"],
            "recorded_at": latest_charge["recorded_at"],
            "note": latest_charge["note"],
        }
    elif latest_reading:
        display = {
            "kind": "reading",
            "percent": latest_reading["percent"],
            "recorded_at": latest_reading["recorded_at"],
            "note": latest_reading["note"],
        }

    drain: dict[str, Any] | None = None
    if latest_charge:
        after = [r for r in readings if r["_at"] >= latest_charge["_at"]]
        if after:
            drain = _drain_block(
                latest_charge["to_percent"],
                latest_charge["_at"],
                after[-1]["percent"],
                after[-1]["_at"],
                basis="since_last_charge",
            )
            if drain["available"] and drain["drain_percent_per_hour"] < 0:
                warnings.append(
                    "Battery rose after the last charge; log a charge event if "
                    "the band was charged again."
                )
        else:
            drain = {
                "available": False,
                "basis": "since_last_charge",
                "reason": "no battery reading after the last charge",
            }
        if latest_charge["from_percent"] is None:
            warnings.append(
                "The last charge has no start percentage; charge rate is unavailable."
            )
        if latest_charge["duration_minutes"] is None:
            warnings.append(
                "The last charge has no duration; charge rate is unavailable."
            )
    else:
        window_start = now - timedelta(hours=24)
        recent = [r for r in readings if r["_at"] >= window_start]
        basis = "last_24h"
        if len(recent) < 2:
            recent = readings
            basis = "all_readings"
        if len(recent) >= 2:
            drain = _drain_block(
                recent[0]["percent"],
                recent[0]["_at"],
                recent[-1]["percent"],
                recent[-1]["_at"],
                basis=basis,
            )
            if drain["available"] and drain["drain_percent_per_hour"] < 0:
                warnings.append(
                    "Battery rose between readings; log a charge event so the "
                    "drain calculation resets at the charge."
                )
        else:
            drain = {
                "available": False,
                "basis": basis,
                "reason": "at least two readings are required",
            }

    if not readings:
        warnings.append("No battery readings have been logged.")
    if not charges:
        warnings.append(
            "No charge events have been logged; charging jumps can distort drain."
        )

    return {
        "reading_count": len(readings),
        "charge_count": len(charges),
        "display": display,
        "latest_reading": _public(latest_reading) if latest_reading else None,
        "latest_charge": _public(latest_charge) if latest_charge else None,
        "drain": drain,
        "charges": [_public(charge) for charge in reversed(charges)],
        "warnings": warnings,
    }


__all__ = [
    "CHARGE_EVENT",
    "READING_EVENT",
    "battery_summary",
    "parse_battery_charges",
    "parse_battery_readings",
]
