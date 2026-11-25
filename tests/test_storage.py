from __future__ import annotations

import json

from fitness_band.storage import SQLiteStore


def test_store_and_query_measurements(tmp_path):
    db = tmp_path / "test.sqlite3"
    with SQLiteStore(db) as store:
        store.upsert_device("AA:BB:CC:DD:EE:FF", "HUAWEI Band HR-TEST")
        session = store.start_session("AA:BB:CC:DD:EE:FF", "test")
        store.add_measurement(
            metric="heart_rate",
            value=95,
            unit="bpm",
            source="test",
            device_address="AA:BB:CC:DD:EE:FF",
            session_id=session,
            ts=1000.0,
            raw=bytes.fromhex("065f"),
            meta={"flags": 6},
        )
        store.add_measurement(
            metric="heart_rate",
            value=96,
            unit="bpm",
            source="test",
            device_address="AA:BB:CC:DD:EE:FF",
            session_id=session,
            ts=1001.0,
        )
        store.add_raw_packet(
            direction="rx",
            characteristic="00002a37-0000-1000-8000-00805f9b34fb",
            data=bytes.fromhex("065f"),
            session_id=session,
            ts=1000.0,
        )
        store.end_session(session)

        rows = store.query_measurements(metric="heart_rate")
        assert len(rows) == 2
        assert rows[0]["value"] == 95
        assert rows[0]["raw_hex"] == "065f"
        assert rows[1]["ts_iso"].startswith("1970-01-01T00:16:41")

        summary = store.summary()
        assert summary["metrics"][0]["n"] == 2
        assert summary["raw_packets"] == 1
        assert summary["devices"][0]["address"] == "AA:BB:CC:DD:EE:FF"


def test_export_csv_and_jsonl(tmp_path):
    db = tmp_path / "test.sqlite3"
    with SQLiteStore(db) as store:
        store.add_measurement(metric="heart_rate", value=70, unit="bpm", source="test", ts=10.0)
        csv_path = tmp_path / "out.csv"
        jsonl_path = tmp_path / "out.jsonl"
        assert store.export_csv(csv_path) == 1
        assert store.export_jsonl(jsonl_path) == 1
        assert "heart_rate" in csv_path.read_text()
        record = json.loads(jsonl_path.read_text().strip())
        assert record["value"] == 70


def test_upsert_device_is_idempotent(tmp_path):
    with SQLiteStore(tmp_path / "test.sqlite3") as store:
        store.upsert_device("AA:BB", "name-one")
        store.upsert_device("AA:BB", "name-two", model="KIM-B19")
        summary = store.summary()
        assert len(summary["devices"]) == 1
        assert summary["devices"][0]["name"] == "name-two"
        assert summary["devices"][0]["model"] == "KIM-B19"
