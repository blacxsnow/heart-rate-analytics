# 10 — Protocol Investigation Notebook

Chronological log of hardware experiments. Times are local (IST, UTC+05:30).
Artifacts are local unless marked sanitised.

Legend: **C** = confirmed on hardware, **L** = likely from sources, **H** =
hypothesis.

---

## N001 — Initial BLE scan

- **Time:** 2026-11-25 15:20
- **Method:** Bleak active scan, 15 s.
- **Result:** normal endpoint `HUAWEI Band 9-<suffix>`, service `0x3802`,
  manufacturer `0x027D = 010300ffff`, address `<redacted>`, RSSI −64.
- **Also present:** a nearby `HUAWEI Band 10-<suffix>`; not ours.
- **Conclusion (C):** normal endpoint uses vendor service `0x3802` in
  advertising, not 0x180D.

## N002 — First GATT enumeration (normal endpoint)

- **Time:** 2026-11-25 15:26
- **Method:** Bleak connect, enumerate services/characteristics/descriptors,
  read DIS.
- **Result:** 9 services, FE86/FE01/FE02 present; no 0x180D. DIS reads returned
  GATT `Unlikely Error`.
- **Conclusion (C):** standard HRS is not exposed in normal mode; DIS is not
  readable without the right state.

## N003 — Enable HR Data Broadcast

- **Time:** 2026-11-25 15:32
- **Action:** user started **Settings → HR Data Broadcasts** on the band.
- **Result:** a new endpoint appeared: `HUAWEI Band HR-<suffix>` at `<redacted>`,
  advertising `0x180D` and TX power +4 dBm.
- **Conclusion (C):** broadcast mode uses a different BLE identity.

## N004 — HRS live capture (30 s)

- **Time:** 2026-11-25 15:33
- **Method:** connect to broadcast endpoint, subscribe `0x2A37`.
- **Result:** 30 notifications in 30.15 s; flags `0x06`; HR 92–100 bpm; no RR.
- **Conclusion (C):** 1 Hz uint8 HR with contact bit.

## N005 — Screen-off soak (212 s)

- **Time:** 2026-11-25 15:33:53 → 15:37:25
- **Method:** long-running logger, screen allowed to time out.
- **Result:** 213 packets, mean period 1.002 s, max gap 1.17 s, zero gaps > 2 s.
- **Conclusion (C):** broadcast survives display-off. Reboot/charging untested.

## N006 — Broadcast endpoint GATT + DIS

- **Time:** 2026-11-25 15:38
- **Method:** reconnect, enumerate, read DIS/body sensor.
- **Result:** 0x180D added; body sensor location `0x02` (wrist). DIS returns
  placeholders (`HUAWEI`, `1.0.0.1`).
- **Conclusion (C):** DIS is not a firmware source.

## N007 — LinkParams on broadcast endpoint

- **Time:** 2026-11-25 15:45
- **Method:** connect `FE02`, write documented LinkParams frame to `FE01`,
  wait 12 s.
- **Result:** no notification; no error at GATT level.
- **Conclusion (C):** FE86 does not answer the handshake on the broadcast
  endpoint. Use the normal endpoint.

## N008 — LinkParams on normal endpoint (attempt 1)

- **Time:** 2026-11-25 15:50
- **Method:** same handshake on `<redacted>` while the phone was still paired.
- **Result:** `failed to discover services, device disconnected`.
- **Conclusion (C):** the normal endpoint rejects/contends an extra link while
  the phone is active.

## N009 — BlueZ-level connect

- **Time:** 2026-11-25 15:52
- **Method:** `bluetoothctl connect` while the phone's Bluetooth was reported
  off.
- **Result:** link connected; GATT attribute list resolved via
  `bluetoothctl gatt list-attributes`.
- **Conclusion (C):** the link can be established; a second Bleak connect raced
  with service discovery. Use the existing link or avoid double-connect.

## N010 — Android reference environment prepared

- **Time:** 2026-11-25 15:55–16:00
- **Actions:**
  - Installed Huawei Health 11.0.0.517 on rooted OnePlus 11R (Android 16).
  - Pulled `base.apk` (99,304,221 bytes).
  - Found HCI snoop logs at `/data/misc/bluetooth/cached_hci/` (`btsnoop_hci_*.cfa`); current log grows.
  - Installed/pushed Frida server 17.27.5 arm64; `frida-ps -U` works.
  - Decompiled APK with JADX 1.5.7.
- **Static findings:**
  - `o/djr.java` = FE86/FE01/FE02 GATT client.
  - `HiChainAuthManager.java` = app-side HiChain wrapper.
  - `o/dkc.java` = HiChain TLV codec.
  - `o/djp.java` = command queue/encryption/slicing.
  - `assets/product_map.json` = `KIM-B19` is the Band 9.
- **Conclusion (C):** the reference environment is ready; pairing capture is
  the next step.

## N012 — Huawei Health command map (static)

- **Time:** 2026-11-25 16:15
- **Method:** JADX 1.5.7 on exact APK 11.0.0.517; inspect
  `com/huawei/hwservicesmgr/remote` and `o/dsw`.
- **Findings (APK-CONFIRMED, hardware unverified):**
  - `0x07/0x17` = `sendSetHeartRateEnableCmd` (automatic HR on/off).
  - `0x07/0x1C` = `sendSetContinueMeasureHeartRateEnableCmd`.
  - `0x07/0x24` = `sendCycleBloodOxygenEnableCmd` (automatic SpO₂).
  - `0x19/0x01` = live HR request; `0x19/0x03` = live HR data/response.
  - `0x20/0x09` = stress calibration payload; `0x20/0x0A` = stress press info.
  - `0x07/0x23` = new resting-HR capability.
  - `0x17/0x17` = heart capability.
- **Interval finding:** the continuous-HR and SpO₂ builders carry only a
  one-byte enable/status TLV. **No sampling interval parameter exists in the
  app's command surface.**
- **Conclusion:** cadence is firmware-controlled; "aggressive configurable
  intervals" is currently unsupported by both the app and the public projects.

## N013 — Pairing capture

- **Status:** pending (user pairing the band with Huawei Health).
- **Plan:** capture E01 (pairing), E02 (init), E03 (HR), E05/E06 (SpO₂),
  E07 (HRV), E08 (history), E09 (reconnect), E10 (app restart).
- **Acceptance:** decoded command timeline with auth, HR and SpO₂ commands.

---

## N014 — HiChain3 handshake captured (CONFIRMED)

- **Time:** 2026-11-25 16:21–16:40
- **Method:** Frida GATT hooks on `:PhoneService` + `javax.crypto.Cipher` hooks;
  forced one Bluetooth reconnect, then opened the Band 9 device page.
- **LinkParams response:** protocol version 1, slice size 244, MTU 244,
  **authVersion 1**, **deviceSupportType 4 (HiChain3)**, bond state 0,
  encryption method 0.
- **Device identity:** `Kimi-B19FB`, firmware **`4.2.0.230(C00M07)`**,
  health model `THREECIRCLECARD`, country `GB` (unique device ID redacted).
- **Security negotiation:** auth mode 4, Android ID, `phoneIdentify`,
  `OnePlus 11R 5G`.
- **HiChain3 JSON:** `isoSalt`, `token`, `peerAuthId`, `operationCode=2`,
  `message=32785`, `groupAndModuleVersion=2.0.1`, `isDeviceLevel=false`;
  final success `0x7F = 0x000186A0`.
- **Conclusion:** this Band 9 uses HiChain3, and the full handshake is now
  captured. Independent auth still requires the account-bound long-term key.

## N015 — AES-GCM TLV decryption (CONFIRMED)

- **Method:** matched each `0x7E` ciphertext from FE01 to the app's
  `Cipher.doFinal` output; plaintext = `doFinal` input.
- **Result:** TLV envelope is `0x7C` flag, `0x7D` 16-byte IV, `0x7E`
  ciphertext + 16-byte GCM tag. AES-GCM, per-session key.
- **Confirmed commands:**
  - `0x07/0x17` automatic HR on/off (`01 01 01` / `01 01 00`)
  - `0x07/0x24` automatic SpO₂ on/off (`01 01 01` / `01 01 00`)
  - `0x07/0x1D` HR high alert (120 bpm)
  - `0x07/0x22` HR low alert (40 bpm)
  - `0x07/0x25` SpO₂ low alert (90%)
  - `0x07/0x03`, `0x0A/0x0B`, `0x0C/0x0D` fitness history
  - `0x2C/0x01` sleep/RRI file request (`sequence_data`,
    `rrisqi_data.bin`), response `0x00023281` = no new file
  - `0x0F/*` file transfer; `0x27/*` version/capability; `0x34/0x01` P2P app
    registry; `0x37/*` data dictionary
- **Conclusion:** the proprietary channel is now readable end-to-end. The
  remaining work is reimplementing HiChain3 and the specific measurement
  streams.

## N016 — Settings toggle experiment: no interval (CONFIRMED)

- **Action:** toggled Continuous heart rate off/on, then Automatic SpO₂ off/on
  in Huawei Health.
- **Captured:**
  - `0x07/0x17` `01 01 00` then `01 01 01`
  - `0x07/0x24` `01 01 00` then `01 01 01`
  - `0x07/0x25` `01 01 01 02 01 5A` (SpO₂ alert 90%)
- **Conclusion:** both are pure on/off commands. **No interval parameter exists
  in the app's command surface.** Aggressive intervals are firmware-controlled;
  this is a hard negative result, not an untested hypothesis.

## N017 — Remaining work

- Reimplement HiChain3 with the captured handshake (requires the long-term
  account-bound key or a factory reset to bind a new key).
- Test `0x19/0x01` live HR and `0x19/0x05` RRI on Band 9.
- Decode the `0x07/0x0B` minute records (HR/SpO₂/steps) and `0x2C` files.
- Decide between HRS (simple, 1 Hz) and proprietary (auth, history, settings).
- Test HRS after reboot/charging for true 24×7.

## N018 — HRS persistence / 24×7 result

- **Baseline:** HR Data Broadcast active; endpoint `HUAWEI Band HR-<suffix>`
  advertising (after releasing a stale Linux link).
- **Finding:** reaching the band's Settings requires exiting HR Data Broadcast.
  A normal restart requires exiting the broadcast to reach Settings, so the mode is off before reboot; auto-resume was not tested.
- **Verified:** screen-off (3.5 min) and host disconnect/reconnect.
- **Not tested:** hard reboot while active, charging.
- **Conclusion:** HRS is continuous while active but does **not** provide
  toggle-free 24×7 across restarts. Proprietary authenticated HR is required
  for that requirement.

---

## Open experiments (next)


1. Read LinkParams on the normal endpoint with the phone disconnected.
2. Determine auth family/version and whether the unit is account-bound.
3. Capture pairing/initialization via HCI + Frida.
4. Test live HR `0x19/0x01` and RRI `0x19/0x05`.
5. Test automatic SpO₂ and verify that no interval parameter exists.
6. Test whether HR broadcast survives reboot and charging.
7. Measure battery drain at 1 Hz HRS.

