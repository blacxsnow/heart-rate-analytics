# 11 — Deliverables Map

Mapping of the original requested deliverables to concrete artifacts.

| Requested deliverable | Artifact | Status |
|---|---|---|
| Existing implementation and literature review | `docs/01_research_report.md` | done |
| BLE reconnaissance utility | `src/fitness_band/ble_scanner.py`, `gatt_inspector.py`, `main.py` | done |
| GATT discovery report | `docs/02_ble_recon.md`, `captures/gatt/gatt_services.json` | done |
| Device and firmware identification | `docs/03_device_identification.md` | model confirmed; firmware pending auth |
| Proposed protocol architecture | `docs/04_protocol_spec.md`, `docs/05_architecture.md` | done |
| Prioritised implementation roadmap | `docs/06_roadmap.md` | done |
| Independent acquisition client | `src/fitness_band/heart_rate.py`, `storage.py`, `main.py` | HRS path done |
| Raw packet preservation | `raw_packets` table + JSONL | done |
| Unit tests for decoding | `tests/test_protocol.py`, `tests/test_hrs.py`, `tests/test_storage.py` | 25 tests pass |
| Integration test on hardware | `band9 hr` live captures | done for HRS |
| Protocol specification with confidence | `docs/04_protocol_spec.md` | living document |
| Lab notebook | `docs/10_lab_notebook.md` | living document |
| Android communication architecture report | `docs/12_huawei_health_architecture.md` | static + runtime done |
| BLE/HCI packet captures | `captures/android/*.btsnoop` (local) + Frida logs | pairing/reconnect captured |
| Relevant classes/methods | `docs/07_android_reference_plan.md` §1, §5–6 | initial list + runtime results |
| Protocol command/response spec | `docs/04_protocol_spec.md` §9, `docs/13_capture_results.md` | confirmed on device |
| Historical data format spec | `0x07/0x0B`, `0x07/0x0D`, `0x2C/0x01` captured | partial; record decoding pending |
| Measurement comparison | HRS live vs band; SpO₂ toggle | HRS done; SpO₂ data pending |
| Firmware feasibility | `docs/08_firmware_investigation.md`, `docs/14_firmware_feasibility.md` | deep desk/hardware review done; low feasibility, no hardware write |

## Reproducible environment

```bash
conda create -n band9 python=3.11
conda activate band9
pip install -r requirements-dev.txt
pip install -e .
```

Android tools (local, not required for the Linux client):

```bash
# HCI log
scripts/pull_hci_log.sh
# Decode btsnoop
python scripts/parse_btsnoop.py captures/android/<file>.btsnoop
# Frida observer
scripts/frida_run.sh
```

## What is deliberately not delivered yet

- A claim that proprietary auth works.
- A claim that SpO₂/HRV/steps/sleep work on this unit.
- A configurable sampling interval.
- Firmware modification or a custom band UI.
- Any secret, MAC, serial or personal health record in the repository.

The project follows the rule: **no feature is marked supported until it is
verified against the physical Band 9.**
