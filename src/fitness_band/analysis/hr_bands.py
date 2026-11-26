"""Configurable HR-band duration and episode analysis."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable
from itertools import pairwise
from typing import Any

import numpy as np
import pandas as pd

MAX_GAP_SECONDS = 5.0

DEFAULT_BAND_SPEC = "<50,50-59,60-69,70-79,80-89,90-99,100-109,110-119,120+"


def _label(minimum: int | None, maximum: int | None) -> str:
    if minimum is None:
        return f"<{maximum + 1}"
    if maximum is None:
        return f"{minimum}+"
    return f"{minimum}–{maximum}"


def _parse_token(token: str, index: int) -> dict[str, Any]:
    text = token.strip()
    if not text:
        raise ValueError("empty band")
    if text.startswith("<"):
        maximum = int(text[1:]) - 1
        minimum = None
    elif text.endswith("+"):
        minimum = int(text[:-1])
        maximum = None
    elif text.startswith(">"):
        minimum = int(text[1:]) + 1
        maximum = None
    elif "-" in text:
        left, right = text.split("-", 1)
        minimum, maximum = int(left), int(right)
    else:
        value = int(text)
        minimum, maximum = value, value
    if minimum is not None and maximum is not None and maximum < minimum:
        raise ValueError(f"invalid band: {text}")
    return {
        "id": f"b{index}",
        "label": _label(minimum, maximum),
        "min": minimum,
        "max": maximum,
    }


def parse_bands(spec: str | Iterable[Any] | None) -> list[dict[str, Any]]:
    """Parse ``<50,50-59,...,120+`` or a JSON list of ranges."""
    if spec is None or spec == "":
        spec = DEFAULT_BAND_SPEC
    if isinstance(spec, str) and spec.strip().startswith("["):
        try:
            parsed = json.loads(spec)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid bands JSON") from exc
        tokens = []
        for item in parsed:
            if isinstance(item, dict):
                minimum = item.get("min")
                maximum = item.get("max")
                tokens.append(
                    "<" + str(maximum + 1)
                    if minimum is None
                    else (str(minimum) + "+" if maximum is None else f"{minimum}-{maximum}")
                )
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                minimum, maximum = item
                tokens.append(
                    "<" + str(maximum + 1)
                    if minimum is None
                    else (str(minimum) + "+" if maximum is None else f"{minimum}-{maximum}")
                )
            else:
                tokens.append(str(item))
        raw_tokens = tokens
    elif isinstance(spec, str):
        raw_tokens = [part for part in re.split(r"[,;]", spec) if part.strip()]
    else:
        raw_tokens = [str(part) for part in spec]

    bands = [_parse_token(token, index) for index, token in enumerate(raw_tokens)]
    if not bands:
        raise ValueError("at least one band is required")
    for previous, current in pairwise(bands):
        prev_max = previous["max"] if previous["max"] is not None else math.inf
        curr_min = current["min"] if current["min"] is not None else -math.inf
        if curr_min <= prev_max:
            raise ValueError("bands must be ascending and non-overlapping")
    return bands


def _band_index(value: float, bands: list[dict[str, Any]]) -> int | None:
    for index, band in enumerate(bands):
        minimum = band["min"] if band["min"] is not None else -math.inf
        maximum = band["max"] if band["max"] is not None else math.inf
        if minimum <= value <= maximum:
            return index
    return None


def _sample_weights(timestamps: pd.Series) -> np.ndarray:
    if len(timestamps) == 0:
        return np.asarray([], dtype=float)
    if len(timestamps) == 1:
        return np.asarray([1.0], dtype=float)
    seconds = pd.DatetimeIndex(timestamps).as_unit("ns").asi8.astype(float) / 1e9
    gaps = np.diff(seconds)
    weights = np.clip(gaps, 0.0, MAX_GAP_SECONDS)
    weights = np.append(weights, float(np.median(weights)) if len(weights) else 1.0)
    return weights


def band_report(
    frame: pd.DataFrame,
    bands: list[dict[str, Any]],
) -> dict[str, Any]:
    if frame.empty:
        return {
            "available": False,
            "bands": [
                {
                    **band,
                    "duration_seconds": 0.0,
                    "percentage": 0.0,
                    "episodes": 0,
                    "longest_episode_seconds": 0.0,
                }
                for band in bands
            ],
            "monitored_seconds": 0.0,
            "daily": [],
            "warnings": ["No measurements in this range."],
        }

    ordered = frame.sort_values("timestamp_utc").reset_index(drop=True)
    values = ordered["heart_rate_bpm"].to_numpy(dtype=float)
    timestamps = ordered["timestamp_utc"]
    weights = _sample_weights(timestamps)
    assigned = np.asarray([_band_index(float(value), bands) for value in values], dtype=object)
    total = float(np.sum(weights))

    durations = np.zeros(len(bands), dtype=float)
    episodes = [0] * len(bands)
    longest = np.zeros(len(bands), dtype=float)

    current_band: int | None = None
    current_duration = 0.0
    previous_time: pd.Timestamp | None = None
    for index, band_index in enumerate(assigned):
        weight = float(weights[index])
        timestamp = timestamps.iloc[index]
        gap = (
            (timestamp - previous_time).total_seconds()
            if previous_time is not None
            else 0.0
        )
        if band_index is None:
            if current_band is not None:
                episodes[current_band] += 1
                longest[current_band] = max(longest[current_band], current_duration)
                current_band = None
                current_duration = 0.0
            previous_time = timestamp
            continue

        if current_band != band_index or gap > MAX_GAP_SECONDS:
            if current_band is not None:
                episodes[current_band] += 1
                longest[current_band] = max(longest[current_band], current_duration)
            current_band = int(band_index)
            current_duration = 0.0
        current_duration += weight
        durations[current_band] += weight
        previous_time = timestamp

    if current_band is not None:
        episodes[current_band] += 1
        longest[current_band] = max(longest[current_band], current_duration)

    band_rows = []
    for index, band in enumerate(bands):
        band_rows.append(
            {
                **band,
                "duration_seconds": round(float(durations[index]), 3),
                "percentage": round(
                    float(durations[index] / total * 100.0) if total > 0 else 0.0, 3
                ),
                "episodes": int(episodes[index]),
                "longest_episode_seconds": round(float(longest[index]), 3),
            }
        )

    daily_map: dict[str, dict[str, float]] = {}
    for index, row in enumerate(ordered.itertuples()):
        band_index = assigned[index]
        if band_index is None:
            continue
        date = row.timestamp_local.date().isoformat()
        bucket = daily_map.setdefault(date, {band["id"]: 0.0 for band in bands})
        bucket[bands[int(band_index)]["id"]] += float(weights[index])

    daily = [
        {
            "date": date,
            "values": {
                band_id: round(value, 3) for band_id, value in daily_map[date].items()
            },
        }
        for date in sorted(daily_map)
    ]

    warnings = []
    if total < 60:
        warnings.append("Less than one minute of monitored time.")
    return {
        "available": True,
        "bands": band_rows,
        "monitored_seconds": round(total, 3),
        "daily": daily,
        "warnings": warnings,
        "note": (
            "Bands are descriptive custom intervals, not diagnostic or "
            "exercise-intensity classifications."
        ),
    }


__all__ = ["DEFAULT_BAND_SPEC", "band_report", "parse_bands"]
