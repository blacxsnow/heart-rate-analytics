"""Tests for the capability-matrix loader."""

from __future__ import annotations

import pytest

from fitness_band.capabilities import CapabilityError, load_matrix, parse_matrix

MINIMAL = {
    "schema_version": 1,
    "entries": [
        {
            "id": "x",
            "measurement": "heart_rate",
            "realtime": "yes",
            "historical": "no",
            "sampling_hz": 1.0,
            "resolution_bits": 8,
            "timestamp_precision": "1 s",
            "access": "GATT",
            "dependencies": [],
            "verification": "confirmed",
            "evidence": ["docs/x.md"],
        }
    ],
}


def test_load_repository_matrix() -> None:
    matrix = load_matrix()

    assert matrix["hr_hqs"].is_usable_realtime
    assert matrix["hr_hqs"].sampling_hz == 1.0
    assert matrix["raw_ppg"].verification == "unknown"
    assert matrix["raw_ppg"].realtime == "unknown"
    assert matrix["ibi_hrv"].verification == "hypothesis"
    assert "hichain3" in matrix["spo2_on_demand"].dependencies


def test_parse_minimal_matrix() -> None:
    matrix = parse_matrix(MINIMAL)
    assert matrix["x"].evidence == ("docs/x.md",)
    assert matrix["x"].notes == ""


def test_rejects_bad_enum() -> None:
    bad = {
        **MINIMAL,
        "entries": [{**MINIMAL["entries"][0], "verification": "probably"}],
    }
    with pytest.raises(CapabilityError):
        parse_matrix(bad)


def test_rejects_duplicate_ids() -> None:
    bad = {"schema_version": 1, "entries": [MINIMAL["entries"][0]] * 2}
    with pytest.raises(CapabilityError):
        parse_matrix(bad)


def test_rejects_missing_field() -> None:
    entry = dict(MINIMAL["entries"][0])
    del entry["access"]
    with pytest.raises(CapabilityError):
        parse_matrix({"schema_version": 1, "entries": [entry]})
