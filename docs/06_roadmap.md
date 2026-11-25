# 06 — Prioritised Implementation Roadmap

Each phase has a hard acceptance criterion. A phase is not "done" because code
exists; it is done when the physical device proves it.

---

## P0 — Independent HR acquisition (DONE)

**Goal:** timestamped HR from the Band 9 with no Huawei Health/account.

- [x] Discover both endpoints.
- [x] Read-only GATT enumeration.
- [x] Standard HRS client.
- [x] Decode flags/HR/contact.
- [x] SQLite + JSONL raw capture.
- [x] Reconnect loop.
- [x] Packet-decoding tests.
- [x] Screen-off soak (213 packets / 212 s).

**Acceptance:** `band9 hr --duration 60` stores >50 measurements and prints
plausible BPM. **Met.**

**Caveat:** this is continuous while the broadcast is active. A normal restart
requires exiting the broadcast to reach Settings, so toggle-free 24×7 is not
met by HRS. See `13_capture_results.md` §7.

---

## P1 — Android reference capture (IN PROGRESS)

**Goal:** a labelled corpus of Huawei Health ↔ Band 9 traffic.

- [x] Rooted phone + Huawei Health installed.
- [x] APK pulled and decompiled.
- [x] HCI snoop log identified.
- [x] Frida server running.
- [x] Pair band with Huawei Health.
- [x] Capture reconnect/initialization and settings experiments.
- [x] Decode FE86 traffic (AES-GCM plaintext recovered).
- [x] Hook GATT and Java crypto (HiChain classes are in a plugin loader).
- [x] Correlate with Gadgetbridge/Huawhoop.
- [x] Record firmware/model (`Kimi-B19FB`, `4.2.0.230(C00M07)`).

**Acceptance:** a decoded capture showing the exact auth sequence, the
measurement-start commands, and the notification payloads for HR/SpO₂.

---

## P2 — Proprietary authentication

**Goal:** authenticate the normal FE86 endpoint from Linux.

- [x] Read LinkParams on the normal endpoint (authVersion 1, HiChain3).
- [x] Capture the complete HiChain3 JSON exchange.
- [ ] Implement/port the matching HiChain3 flow (needs the account-bound key).
- [ ] Store keys locally with 0600 permissions.
- [ ] Read product info, firmware, battery, supported services/commands.
- [ ] Reconnect with a stored session key.
- [ ] Unit tests with captured test vectors.

**Decision point:** if auth requires an account-derived key and the band is
bound, ask for explicit consent to factory reset. Back up all on-device data
first. Never reset silently.

**Acceptance:** a second independent run authenticates with the stored key and
reads the real firmware string.

---

## P3 — Real-time HR, SpO₂, HRV

**Goal:** the measurements the user actually wants, at the best available rate.

- [ ] Test `0x19/0x01` live HR (`hr_type=1`) on Band 9.
- [ ] Test `0x19/0x05` RRI/SQI (`hr_type=3`) for HRV.
- [ ] Measure actual notification rate and jitter.
- [x] Test automatic SpO₂ toggle (`0x07/0x24`) — on/off only, confirmed.
- [ ] Determine whether SpO₂ is live or only historical.
- [x] Confirm there is no app-level sampling interval.
- [ ] Search for hidden interval TLVs; otherwise document the firmware limit.
- [ ] Compare HRS and proprietary HR simultaneously/alternately.

**Acceptance:** a 10-minute live HR capture at >1 Hz, or a documented proof that
the firmware caps it at 1 Hz. SpO₂ either live or explicitly classified as
historical-only.

---

## P4 — Historical sync

**Goal:** steps, sleep, SpO₂, resting HR, stress, workouts.

- [ ] Fitness minute history (`0x07/0x0A`).
- [ ] Sleep history / TruSleep.
- [ ] SpO₂ samples.
- [ ] Resting HR.
- [ ] Stress / HRV summaries.
- [ ] Timestamp and unit validation against the phone's Huawei Health display.
- [ ] Incremental sync cursor.

**Acceptance:** one day of history matches Huawei Health within a defined
tolerance, with raw packets retained.

---

## P5 — Gateway and interoperability

**Goal:** make the data reusable without touching Huawei code.

- [ ] REST endpoints (`/health`, `/measurements`, `/devices`).
- [ ] WebSocket stream.
- [ ] MQTT publisher with configurable topic.
- [ ] CSV/JSON export (done).
- [ ] Standard HRS peripheral re-broadcast (BlueZ or ESP32).
- [ ] systemd service and health checks.

**Acceptance:** an external client receives live HR over WebSocket/MQTT and a
standard HR monitor app sees the re-broadcast service.

---

## P6 — Firmware investigation (only if P2–P4 are insufficient)

**Goal:** only if software cannot deliver the required sampling/battery/UI.

- [ ] Identify OTA package format and signing.
- [ ] Check for public Band 9 firmware analysis.
- [ ] Map debug pads/UART/SWD only if non-destructive.
- [ ] Establish a recovery path before any write.
- [ ] Do not flash without a verified recovery image.

**Acceptance:** a written feasibility report, not a flashed device.

See `08_firmware_investigation.md` for the risk analysis.

---

## Explicit non-goals for now

- Raw PPG waveform extraction (almost certainly not exposed).
- Rewriting the band UI/firmware.
- Bypassing Huawei account security.
- Claiming SpO₂/HRV/steps support before device verification.
