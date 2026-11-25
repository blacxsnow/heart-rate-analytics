from __future__ import annotations

import pytest

from fitness_band.hrs import HeartRateParseError, parse_heart_rate_measurement


def test_burst_packet_from_band9():
    # Captured from the physical Band 9: 95 bpm, contact detected.
    m = parse_heart_rate_measurement(bytes.fromhex("065f"))
    assert m.heart_rate_bpm == 95
    assert m.sensor_contact is True
    assert m.energy_expended_kj is None
    assert m.rr_intervals_s == []
    assert m.flags == 0x06


def test_uint16_heart_rate_and_contact_not_detected():
    m = parse_heart_rate_measurement(bytes.fromhex("030100"))
    assert m.heart_rate_bpm == 1
    assert m.sensor_contact is False


def test_energy_expended():
    m = parse_heart_rate_measurement(bytes.fromhex("0e5f3412"))
    assert m.heart_rate_bpm == 95
    assert m.energy_expended_kj == 0x1234
    assert m.sensor_contact is True


def test_rr_intervals():
    # flags 0x16 = uint8 + contact + RR. 1024 raw = exactly 1.0 s.
    m = parse_heart_rate_measurement(bytes.fromhex("165f00040008"))
    assert m.heart_rate_bpm == 95
    assert m.rr_intervals_s == pytest.approx([1.0, 2.0])
    assert m.rr_intervals_ms == pytest.approx([1000.0, 2000.0])


def test_no_contact_support_reports_none():
    m = parse_heart_rate_measurement(bytes.fromhex("005f"))
    assert m.sensor_contact is None


@pytest.mark.parametrize("raw", ["", "01", "0100", "0e5f", "165f00"])
def test_truncated_packets_rejected(raw):
    with pytest.raises(HeartRateParseError):
        parse_heart_rate_measurement(bytes.fromhex(raw))
