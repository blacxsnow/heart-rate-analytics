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
| `13_capture_results.md` | Runtime reference capture: HiChain3, AES-GCM, confirmed commands, interval result |
| `14_firmware_feasibility.md` | Deep firmware/hardware inspection: Apollo3 secure boot, OTA path, SWD, recovery, staged plan |
| `15_firmware_static_analysis.md` | Track A: image map and load addresses, OpenHarmony architecture, BLE/HiChain3/HKS, PPG and storage, UI independence |
| `16_hichain3_streams.md` | Track B: auth flow, band-side HiChain3 evidence, measurement command map, remaining gaps, independent-auth options |
| `17_acquisition_system.md` | 24×7 acquisition daemon, database contract, reliability, systemd deployment, dashboard, analysis, validation, HR-broadcast experiment |
| `18_acquisition_quality_report.md` | Deployment and quality validation: tests, simulation metrics, crash recovery, empty real DB, pending reboot/BLE checks |

## Current bottom line

- **Working today:** account-free, timestamped 1 Hz heart rate over standard
  BLE HRS (`0x180D/0x2A37`), stored in SQLite/JSONL, with reconnect.
- **Captured and decoded:** HiChain3 authentication handshake, AES-GCM FE86
  TLV encryption, automatic HR/SpO₂ settings, fitness-history and file-request
  commands.
- **Not yet working independently:** reproducing HiChain3 from Linux (requires
  the account-bound key or a consented factory reset), live proprietary HR/RRI,
  and historical record field decoding.
- **Confirmed hardware limit:** Huawei Health exposes only on/off for
  automatic HR and SpO₂; there is no sampling-interval control.
- **24×7 caveat:** a normal restart requires exiting the HRS broadcast to reach
  Settings, so the mode is off before reboot; auto-resume was not tested.
  Proprietary HiChain3 authentication is the path to a persistent mode.
- **Firmware architecture (static):** OpenHarmony-based wearable; `xip_code.bin`
  loads at `0x06040000`; the band itself implements HiChain3 with HKS-backed
  group keys in `/user/deviceauth`; PPG, sleep/OSA, RRI and health history are
  file-backed services.
- **Live authenticated capture (2026-11-25):** full HiChain3 JSON exchange,
  32-byte per-session AES-GCM key, HR-history window/records (`0x07/0x0A/B`,
  `0x0C/D`), SpO₂ window queries (`0x1E/0x1F/0x26`, no data yet) and an
  `rrisqi_data.bin` request (no file). See `16_hichain3_streams.md`.
- **SpO₂ negative result:** two band-side spot measurements (98–99%, 97%) were
  not streamed to the phone; only a periodic `0x25/0x01` poll was seen. The
  band’s `spo2.bin` file is retrievable via `0x2C`, but its records are older
  PPG/OSA features, not the spot reading.
- **24×7 acquisition service:** `band9-acquire` daemon + SQLite WAL + separate
  FastAPI dashboard + separate read-only analysis CLI. Deployed as user
  services with lingering; see `17_acquisition_system.md`.
- **Capability matrix:** `capabilities/matrix.yaml` (validated by
  `fitness_band.capabilities`) separates confirmed, partial, hypothesis and
  unknown streams.
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
