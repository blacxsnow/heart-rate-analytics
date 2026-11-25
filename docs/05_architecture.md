# 05 — Proposed Architecture

The design separates **acquisition** (BLE + Huawei specifics) from
**distribution** (APIs/storage), so the Huawei protocol never leaks into
downstream research code.

```
┌─────────────────────────────────────────────────────────────┐
│ Acquisition host (Linux, Python)                            │
│                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────────┐  │
│  │ Endpoint     │   │ HRS client   │   │ Proprietary    │  │
│  │ manager      │──▶│ 0x180D/2A37  │   │ FE86 client    │  │
│  │ (scan/lock)  │   │ (verified)   │   │ (auth pending) │  │
│  └──────────────┘   └──────┬───────┘   └───────┬────────┘  │
│                            │                   │           │
│                     ┌──────▼───────────────────▼───────┐   │
│                     │ Normalised measurement pipeline  │   │
│                     │ timestamp → metric → quality     │   │
│                     └──────┬───────────────────┬───────┘   │
│                            │                   │           │
│                     ┌──────▼──────┐     ┌──────▼────────┐  │
│                     │ SQLite WAL  │     │ Raw JSONL     │  │
│                     │ (query)     │     │ (forensics)   │  │
│                     └──────┬──────┘     └───────────────┘  │
│                            │                               │
│  ┌─────────────────────────▼────────────────────────────┐  │
│  │ Distribution (independent modules)                    │  │
│  │  REST · WebSocket · MQTT · CSV/JSON · HRS re-broadcast│  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 1. Layers

### 1.1 Transport

- `ble_scanner.py`: discovers both endpoints, merges advertisements, records
  RSSI/manufacturer data.
- `device_manager.py`: resolves an endpoint by name/UUID; enforces one active
  link; connection helpers.
- BlueZ is the Linux backend. A future ESP32 gateway can reuse the protocol
  layer over NimBLE.

### 1.2 Protocol

- `protocol.py`: LPv2 framing, CRC16-HQXQ, TLV varint, slicing, LinkParams.
- `authentication.py`: LinkParams probe now; HiChain/HiChain3 state machine
  later. Keys live outside the repo, mode 0600.
- `heart_rate.py`: standard HRS acquisition.
- Future `huawei_health.py`: proprietary live HR/RRI, SpO₂, fitness history,
  sleep, battery, product info.

### 1.3 Normalised model

Every measurement is:

```
timestamp_utc, metric, value, unit, source, quality, raw_hex, meta_json
```

Device-specific fields (Huawei service/command, flags, contact bit, packet
counter) go into `meta_json`, never into the metric name.

Metric names are stable and vendor-neutral:

```
heart_rate            bpm
rr_interval           ms
resting_heart_rate    bpm
spo2                  percent
steps                 count
sleep_stage           enum
stress_score          score
skin_temperature      celsius
battery               percent
```

### 1.4 Storage

- SQLite with WAL for one host and one band. Indexed by metric/time and
  device/time.
- Raw JSONL and raw packet rows preserve every BLE payload.
- CSV/JSONL export for analysis.
- If the project grows to many devices/high rate, the same interface can be
  backed by TimescaleDB or InfluxDB.

### 1.5 Distribution

Independent modules, not coupled to BLE:

| Interface | Direction | Status |
|---|---|---|
| SQLite | local query | implemented |
| CSV / JSONL | file export | implemented |
| REST | pull | planned |
| WebSocket | push | planned |
| MQTT | push | planned |
| Standard HRS re-broadcast | BLE peripheral | planned (BlueZ GATT server or ESP32) |

The HRS gateway is the interoperability escape hatch: once the Linux host has
normalised HR, it can re-publish `0x180D/0x2A37` so existing apps (OBS, HR
monitors, research tools) work unchanged.

## 2. 24×7 acquisition strategy

There are three options, with different trade-offs:

### Option A — keep HR Data Broadcast on (verified, simplest)

- Pros: no auth, no Huawei account, standard HRS, survives screen-off and host
  disconnect.
- Cons: user must start it after reboot/charge (until proven otherwise); no
  SpO₂/HRV; fixed 1 Hz.
- This is the current default.

### Option B — proprietary continuous HR (auth required)

- Authenticate on the normal endpoint, enable automatic HR / live HR stream.
- Pros: no broadcast toggle, potentially access to SpO₂/history/config.
- Cons: auth/firmware risk, exclusive link, may interfere with phone pairing.
- Not yet verified.

### Option C — hybrid scheduler

- Keep HRS for real-time HR.
- Periodically disconnect HRS, connect the proprietary endpoint for history/SpO₂
  sync, then return to HRS.
- Pros: best coverage without permanent auth.
- Cons: gaps during sync; whether the band can re-enter broadcast mode without
  user input is unknown.

The scheduler should be a policy object, not hard-coded in the BLE client.

## 3. Reliability

- Reconnect with exponential backoff (2 → 30 s), rescan on failure.
- Detect stale data (no packet for N seconds) and recycle the link.
- One connection owner per process (file lock) to avoid BlueZ contention.
- SQLite writes are transactional; raw packets are written before decoding.
- Log connection state transitions as events.
- Never let a parse error kill the acquisition loop.

## 4. Privacy and key handling

- MACs, serials, keys and raw health data are local-only and gitignored.
- Auth keys stored in a separate file with mode 0600, never in the DB.
- Public reports are generated from sanitised JSON, not raw captures.
- The Android phone is a lab instrument, not a runtime dependency.

## 5. Deployment

- `band9 hr` for a foreground session.
- systemd unit for a long-running service (future).
- Optional container, but BLE access needs host D-Bus/BlueZ, so a container is
  less convenient than a systemd service.
- Configuration via environment variables and CLI flags; no MAC in source.

## 6. Module map

| Requirement | Module | Status |
|---|---|---|
| Discover | `ble_scanner.py` | done |
| Enumerate GATT | `gatt_inspector.py` | done |
| Auth | `authentication.py` | LinkParams probe only |
| Protocol | `protocol.py` | framing/TLV/LinkParams |
| HR | `heart_rate.py` | HRS verified |
| Reconnect | `heart_rate.py`, `device_manager.py` | verified basic loop |
| Storage | `storage.py` | done |
| Export | `storage.py` | CSV/JSONL |
| REST/WS/MQTT | future `gateway/` | not started |
| HRS re-broadcast | future `gateway/hrs_peripheral.py` | not started |
