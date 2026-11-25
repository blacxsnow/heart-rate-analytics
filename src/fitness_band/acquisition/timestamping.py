"""Timestamp helpers for observations.

The standard HRS notification contains no measurement timestamp. We therefore
record the PC reception time as the observation time and mark
``measurement_time_known=False``; the acquisition layer never pretends the
reception time is the sensor acquisition time.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class ObservationTime:
    epoch: float
    utc_iso: str
    local_iso: str
    tz_offset_minutes: int
    monotonic: float

    def as_flags(self) -> dict:
        return {
            "timezone": self.local_iso[-6:] if self.local_iso else None,
            "tz_offset_minutes": self.tz_offset_minutes,
            "measurement_time_known": False,
            "time_source": "pc_reception",
        }


def now_observation(epoch: float | None = None, monotonic: float | None = None) -> ObservationTime:
    epoch = time.time() if epoch is None else epoch
    monotonic = time.monotonic() if monotonic is None else monotonic
    utc = datetime.fromtimestamp(epoch, tz=UTC)
    local = utc.astimezone()
    offset = local.utcoffset()
    offset_minutes = int(offset.total_seconds() // 60) if offset is not None else 0
    return ObservationTime(
        epoch=epoch,
        utc_iso=utc.isoformat(timespec="milliseconds"),
        local_iso=local.isoformat(timespec="milliseconds"),
        tz_offset_minutes=offset_minutes,
        monotonic=monotonic,
    )


__all__ = ["ObservationTime", "now_observation"]
