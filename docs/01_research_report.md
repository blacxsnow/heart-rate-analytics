# 01 — Existing Implementations and Literature Review

**Project:** Huawei Band 9 independent BLE acquisition
**Date:** 2026-11-25
**Device under test:** Huawei Band 9, model `KIM-B19`, advertising suffix `<redacted>`

This review answers one question before code is written: *what has already been
implemented, and what actually needs reversing?*

---

## Executive summary

1. **Continuous, account-free heart rate is already possible without reversing
   the proprietary protocol.** The Band 9 exposes the standard Bluetooth SIG
   Heart Rate Service (`0x180D` / `0x2A37`) when the user starts
   **Settings → HR Data Broadcasts**. This was verified on the physical device:
   30 notifications in 30 s, then 213 notifications over 212 s with the display
   off (max gap 1.17 s). No Huawei account, pairing, bonding or authentication is
   involved.
2. **Gadgetbridge already supports the Band 9** as an experimental, pair-free
   Huawei device (PR #3771). Its Huawei backend is the most complete open
   implementation of the proprietary `FE86` channel, including authentication,
   notifications, fitness history, SpO₂ history, sleep, workouts and settings.
3. **Huawhoop (Band 10) is the most useful recent protocol notebook.** It
   documents the LPv2 frame format, HiChain3, live RRI/HRV, real-time HR,
   fitness-minute history and sleep-sequence HRV, with a Python implementation.
   Band 10 is a close sibling of Band 9; its findings are strong hypotheses,
   not confirmed Band 9 behaviour.
4. **The proprietary channel is not needed for the minimum outcome, but is
   needed for SpO₂, historical sync, interval control, battery/firmware
   identity and 24×7 operation that survives reboots.** Authentication is the
   gate.
5. **Do not reinvent the framing/auth code.** Port Gadgetbridge's `HuaweiCrypto`
   and `HuaweiPacket`, and use `huawei-lpv2`/Huawhoop as Python references.

---

## 1. Gadgetbridge

**Project:** Freeyourgadget/Gadgetbridge (Android, AGPLv3)
**Relevant backend:** `app/src/main/java/nodomain/freeyourgadget/gadgetbridge/service/devices/huawei/`
**Device coordinator:** `.../devices/huawei/huaweiband9/HuaweiBand9Coordinator.java`

### 1.1 Device support

Gadgetbridge's public device page lists **Huawei Band 9** with
`has_flag__feature_most` and `has_flag__pair_free`, added in PR #3771.
The coordinator is marked `isExperimental()` and matches the advertising name
prefix:

```java
public static final String HU_BAND9_NAME = "huawei band 9-";
```

The coordinator extends `HuaweiLECoordinator`, uses the Huawei `FE86` service
for scanning, and sets `BONDING_STYLE_NONE` (no Android bond).

**Limitation:** PR #3771 and issue #3784 report that after a Band 9 firmware
update to `3.1.0.31` (after pairing with Huawei Health), pairing/authentication
can fail. The workaround in the issue makes Band 9 and Band 7 work but breaks
Band 8/GT4 in some cases. This is a firmware-dependent auth regression, not a
GATT/transport problem. Our device's real firmware is not yet known (see
`03_device_identification.md`).

### 1.2 GATT transport

`HuaweiConstants.java` defines:

```java
UUID_SERVICE_HUAWEI_SERVICE = ...FE86
UUID_CHARACTERISTIC_HUAWEI_WRITE = ...FE01
UUID_CHARACTERISTIC_HUAWEI_READ  = ...FE02
UUID_SERVICE_HUAWEI_SDP = 82FF3820-8411-400C-B85A-55BDB32CF060
```

`HuaweiLESupport.java` registers GAP, GATT, Device Information, HID and FE86,
enables notifications on `FE02`, and delegates all packets to
`HuaweiSupportProvider`.

### 1.3 Authentication

`HuaweiSupportProvider.initializeDevice()` performs:

1. `GetLinkParamsRequest` (unencrypted, `DeviceConfig 0x01/0x01`)
2. `GetDeviceStatusRequest`
3. Security negotiation (`DeviceConfig 0x01/0x33`) to select the auth family
4. One of:
   - **HiChain / HiChain3** (`authType == 0x0186A0` or 5/6): PIN/account-based
     handshake (`GetPincodeRequest`, `GetHiChainRequest`)
   - **HiChain Lite** (`authType == 1/2`): random 16-byte secret key, auth
     challenge/response, bond params
   - **Normal** (no HiChain): same challenge/response without the lite digest
5. Post-auth init: product info, time, battery, supported services, supported
   commands, expanded capabilities, etc.

Key files:

| File | Role |
|---|---|
| `devices/huawei/HuaweiCrypto.java` | AES-CBC/GCM, HMAC-SHA256, PBKDF2, secret-key derivation, digest challenge |
| `devices/huawei/HuaweiPacket.java` | LP frame layout, slicing, CRC, TLV encryption |
| `devices/huawei/HuaweiTLV.java` | TLV encode/decode, nested containers |
| `service/.../requests/GetLinkParamsRequest.java` | link params + auth version/device support type |
| `service/.../requests/GetSecurityNegotiationRequest.java` | auth family negotiation |
| `service/.../requests/GetAuthRequest.java` | challenge/response |
| `service/.../requests/GetBondParamsRequest.java` | bond params / encryption counter |
| `service/.../requests/GetPincodeRequest.java` | PIN retrieval (HiChain) |

**Important for us:** Gadgetbridge creates a random 16-byte `authkey` itself
when no key exists. For a Band 9 that is already bound to Huawei Health, the
watch may expect the Huawei-account-derived key; this is why the account-ID
workaround exists. A factory reset is the clean way to bind the watch to an
independent key, but it destroys on-device history and must be consented to.

### 1.4 Physiological data

| Feature | Gadgetbridge implementation | Confidence for Band 9 |
|---|---|---|
| Heart rate logging/history | `FitnessData` (`0x07`), `HuaweiSampleProvider` | Likely; experimental device |
| Automatic HR on/off | `FitnessData.EnableAutomaticHeartrate` (`0x07/0x17`) | Command exists; Band 9 support unverified |
| Resting HR notification | `FitnessData.NotifyRestHeartRate` (`0x07/0x23`) | Command exists; unverified |
| Automatic SpO₂ on/off | `FitnessData.EnableAutomaticSpo` (`0x07/0x24`) | Command exists; unverified |
| SpO₂ history | `HuaweiSpo2SampleProvider` | Likely; experimental |
| Sleep / TruSleep | `HuaweiTruSleepParser`, `SetTruSleepRequest` | Likely |
| Skin temperature | `SetSkinTemperatureMeasurement` | Device-dependent |
| Real-time HR / RR | `Workout.NotifyHeartRate` (`0x19/0x17`) capability request | Not a proven live stream in GB |
| Workout data | `Workout` packets, `HuaweiWorkoutGbParser` | Likely |

Gadgetbridge's public "Huawei/Honor" page explicitly lists **"Real time data"**
as *not supported (yet)* for Huawei. This matches our conclusion: the standard
HRS path is the only verified real-time path today; the proprietary live stream
must be proven against the Band 9.

### 1.5 References

- <https://gadgetbridge.org/gadgets/wearables/huawei-honor>
- <https://gadgetbridge.org/basics/pairing/huawei-honor-pairing>
- <https://codeberg.org/Freeyourgadget/Gadgetbridge/issues/3784>
- Local mirror used for source review:
  `/tmp/opencode/Gadgetbridge/app/src/main/java/nodomain/freeyourgadget/gadgetbridge/...`

---

## 2. Huawhoop (Huawei Band 10)

**Project:** `Kuberwastaken/Huawhoop` — an independent Band 10 data platform.
**Why it matters:** it is a recent, code-level, empirically tested LPv2/HiChain3
implementation with a detailed `FINDINGS.md`.

### 2.1 Verified Band 10 capabilities

From `FINDINGS.md`:

- HiChain3 first auth and stored-key reconnect work.
- Fitness history: 24 h produced 6019 steps, 159 sleep minutes, **472 HR
  samples**, **74 SpO₂ samples**.
- Live RRI/HRV: `svc=0x19/cmd=0x01` with `hr_type=3`, notifications on
  `cmd=0x05`, 50–70 s window, RMSSD and Huawei stress score; 81 RRI samples,
  48 clean intervals, RMSSD 53.7 ms.
- Real-time HR: the decompiled Huawei Health `serviceId_25.json` maps service
  `0x19` command `1` to `hr_type` and command `3` to a real-time HR list.
  Empirically, `hr_type=1` opens a real-time HR stream on `cmd=0x03` using
  extended TLV tags `0x81/0x82`.
- Sleep-sequence HRV via `sequence_data/SLEEP_DETAILS` (dictionary 700013),
  including `avgHrv`, HRV baseline, SpO₂ and breath rate.
- Weather push and watchface operations (out of scope here).

### 2.2 Protocol facts

From `FINDINGS.md` and `connect.py`:

- GATT: `FE01` write, `FE02` notify.
- Unsliced frame: `5A LL LL 00 SS CC <TLV...> CRC16`, length =
  `len(SS CC TLV)+1`.
- CRC16-HQXQ (`binascii.crc_hqx(..., 0)`), big-endian.
- Sliced frames: slice byte 1/2/3 at offset 3, shared flag counter at offset 4.
- Auth: HiChain3, `deviceSupportType=4`, `authType=0x05`, auth version 1,
  `enc_method=0x00` (AES-CBC for PIN decryption).
- TLV lengths are big-endian base-128 varints.
- Nested containers use tags such as `0x81`, `0x82`, `0x83`, `0x84`.

### 2.3 Caveats

- Band 10 ≠ Band 9. Command support is gated by the device's supported-services
  and supported-commands bitmaps. Never assume a Band 10 command exists on the
  Band 9.
- Huawhoop's Band 10 went through a factory reset to establish first auth; this
  is a data-destroying step.
- The repository includes a 458 MB decompiled Huawei Health tree and a
  Gadgetbridge snapshot, which are useful references but are not Band 9 proof.

### 2.4 References

- <https://github.com/Kuberwastaken/Huawhoop>
- Local: `/tmp/opencode/Huawhoop/FINDINGS.md`, `connect.py`,
  `Huawei-Health-Decompiled/`

---

## 3. Band Companion (Huawei Band 10)

**Project:** `MrTrotid/Band-Companion` — autonomous Android companion and
reverse-engineered BLE engine for Band 10 (`NOR-B19` / `NOR-B29`).
**Relevance:** confirms the architectural facts independently of Huawhoop:

- vendor service `0xFE86`
- LPv2 / LPW TLV framing
- HiChain3 application-layer authenticated encryption
- no standard 0x180D physiological broadcast in normal mode
- all management/sensor data inside the proprietary channel

Treat its prose as a secondary source; its protocol claims align with
Gadgetbridge and Huawhoop.

---

## 4. huawei-lpv2 (Python)

**Project:** `zyv/huawei-lpv2` — pure-Python Huawei BLE Link Protocol v2,
originally for older Band/ Watch devices.

Useful, directly reusable pieces:

- `huawei/protocol.py`: frame encode/decode, CRC16, TLV varint, AES-CBC
  session encryption, HMAC/PBKDF2 challenge-response, slicing.
- `huawei/services.py`: protocol/command IDs and result tags.
- `band_lpv2.py`: Bleak connection loop.

Limitations: older auth versions (V1/V2/V3), no HiChain3, no Band 9-specific
service map. It is a good codec reference, not a Band 9 client.

---

## 5. Standard-HRS projects and vendor documentation

- `fishuvn/huawei-hr-overlay` reads standard `0x180D/0x2A37` from Huawei
  Watch/Band devices, including Band 9, with no Huawei SDK. Its supported-device
  list is consistent with our hardware result, but the actual verification for
  this project is our own 213-packet capture.
- Huawei's official support page documents **HR Data Broadcasts**: the wearable
  continuously measures HR and shares it with third-party devices/apps.
- Pulsoid's setup guide confirms the same menu path on Band 8/9/10 and notes
  that the broadcast can continue during a workout.

**Consequence:** the Band 9's standard HRS is a supported product feature, not a
reverse-engineering accident. It is the correct primary integration point for
real-time HR.

---

## 6. Academic / conference reverse engineering

- Christian Kudera, **"All Your Fitness Data Belongs to You: Reverse Engineering
  the Huawei Health Android App"**, easterhegg 2019.
  - Slides: <https://www.sba-research.org/wp-content/uploads/2019/04/easterhegg19.pdf>
  - Talk: <https://media.ccc.de/v/eh19-186-all-your-fitness-data-belongs-to-you-reverse-engineering-the-huawei-health-android-app>
- Documents LPv2 message structure, the LinkParams handshake, CRC, TLV layout,
  the encrypted local Health database, and the Huawei Health APK analysis
  method (JADX + Frida + signature patching).
- Still the best public explanation of the *shape* of the protocol; command
  coverage is dated.

---

## 7. What is already solved vs what remains

### Already solved by existing work

- BLE discovery and GATT map of Huawei wearables.
- LPv2 framing, CRC, TLV, slicing.
- HiChain / HiChain Lite / HiChain3 authentication families.
- Band 9 Gadgetbridge support and pair-free operation.
- Standard HRS heart-rate broadcast on Band 9.
- Historical fitness/sleep/SpO₂ parsing in Gadgetbridge.
- Live RRI/HRV and real-time HR experiments on Band 10 (Huawhoop).

### Remains genuinely unresolved for this Band 9

1. Which auth family this specific firmware uses (LinkParams response).
2. Whether the normal endpoint can be authenticated without a factory reset,
   given prior phone pairing.
3. Whether `0x19/0x01` live HR and `0x19/0x05` RRI work on Band 9.
4. Whether HR/SpO₂ measurement intervals are configurable, or firmware-fixed.
5. Whether SpO₂ can be streamed in real time or only synced historically.
6. Whether HR Data Broadcast survives reboot, charging and multi-day operation.
7. Whether the Band 9 exposes any raw PPG or only derived metrics (almost
   certainly the latter).

These are the targets of the Android reference capture and the next hardware
experiments.

---

## 8. Design consequences

- **Do not block the working HRS path on proprietary auth.** Ship the HRS
  acquisition client now; add proprietary capabilities behind a feature flag.
- **Use Gadgetbridge as the specification of record** for auth and packets, and
  verify each command on the Band 9 before claiming support.
- **Use the rooted phone only to observe.** The final client must speak BLE
  directly from Linux.
- **Keep raw captures and a confidence tag for every command.** A command copied
  from Band 10 is a hypothesis until the Band 9 answers.
