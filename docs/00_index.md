# 00 — Documentation Index

Start here.

| Document | Contents |
|---|---|
| `01_research_report.md` | Gadgetbridge, Huawhoop, Band Companion, huawei-lpv2, HRS projects, academic work, and what remains unresolved |
| `02_ble_recon.md` | Advertising endpoints, GATT maps, verified 1 Hz HRS capture, screen-off soak |
| `03_device_identification.md` | `KIM-B19`, DIS placeholders, firmware unknowns, rooted-phone environment |
| `04_protocol_spec.md` | LPv2 framing, CRC, TLV, LinkParams, auth families, command table, confidence tags |
| `05_architecture.md` | Acquisition/distribution split, 24×7 strategies, storage, gateway |
| `06_roadmap.md` | P0–P6 with acceptance criteria |
| `07_android_reference_plan.md` | HCI/Frida/static-analysis methodology and E01–E13 experiment matrix |
| `08_firmware_investigation.md` | Desk review, risks, recovery requirements, "measurement-only UI" reality check |
| `09_measurement_matrix.md` | Real-time vs historical vs device-internal vs app-derived metrics |
| `10_lab_notebook.md` | Chronological experiment log (N001–N013) |
| `11_deliverables.md` | Deliverables map and reproducibility commands |
| `12_huawei_health_architecture.md` | Static architecture of Huawei Health 11.0.0.517 (BLE stack, HiChain, command builders, storage, native libs) |

## Current bottom line

- **Working today:** account-free, timestamped 1 Hz heart rate over standard
  BLE HRS (`0x180D/0x2A37`), stored in SQLite/JSONL, with reconnect.
- **Not yet working:** proprietary FE86 authentication, SpO₂, HRV, history,
  configurable intervals.
- **In progress:** rooted-phone reference capture (Huawei Health 11.0.0.517).
- **Not attempted:** firmware modification.

## Quick commands

```bash
band9 doctor
band9 endpoints
band9 gatt --endpoint hr_broadcast --subscribe 20
band9 hr --duration 60
band9 summary
python -m pytest -q
```
