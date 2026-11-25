# 12 — Huawei Health Communication Architecture (Static Analysis)

**App:** `com.huawei.health` 11.0.0.517 (versionCode 1010050517)
**APK:** 99,304,221 bytes, pulled from the rooted OnePlus 11R
**Decompiler:** JADX 1.5.7 (`--no-res`)
**Status:** static architecture report, now cross-checked against a runtime
capture. Class semantics are **APK-CONFIRMED**; device behaviour is confirmed
where noted in `13_capture_results.md`.

Runtime result (2026-11-25): the Band 9 negotiated **HiChain3** (authVersion 1,
deviceSupportType 4), FE86 TLVs used **AES-GCM**, and the decrypted command
sequence matched the static builders below. See `13_capture_results.md`.

---

## 1. High-level stack

```
UI (Kotlin/Java, com.huawei.ui.*, com.huawei.health.*)
        │
        ▼
Device managers (com.huawei.hwservicesmgr.remote.*, o.*)
  HwHeartRateManager, HwHeartAbility, RriHeartRateSendCommandUtil,
  HwDevicePeriodRriFileManager, FitnessSendCommandUtil (o.dsw)
        │  DeviceCommand{serviceID, commandID, data, needEncrypt, needAck}
        ▼
Command transport (o.djp = BTDeviceSendCommandUtil)
  queue, timeouts, V1/V2 conversion, slicing, encryption
        │
        ▼
GATT client (o.djr = BTDeviceBLEService)
  FE86 / FE01 / FE02; fallback 0x0200 / 0x0203 / 0x0202
        │
        ▼
Android BluetoothGatt
        │
        ▼
Band 9 (KIM-B19)
```

Authentication is not implemented in the GATT client. It is delegated to the
HiChain stack:

```
o.dkc (HiChain command TLV codec)
  → com.huawei.hwbtsdk.hichain.HiChainAuthManager
    → com.huawei.security.deviceauth.HwDeviceAuthManager (HiChain SDK)
      → onDataTransmit(byte[]) → o.djp → FE01
```

## 2. GATT client — `o.djr` (`BTDeviceBLEService`)

Evidence:

- `onServicesDiscovered` looks up
  `0000fe86-0000-1000-8000-00805f9b34fb`.
- Write characteristic `0000fe01-...`; notify characteristic `0000fe02-...`.
- Fallback service `00000200-...`, write `00000203-...`, notify `00000202-...`
  for older devices.
- Enables notifications by writing the standard CCCD
  (`00002902-...`) with `ENABLE_NOTIFICATION_VALUE`.
- Uses a `HandlerThread` + message queue for writes and a resend/timeout path.
- Logs `Device-->SDK` values via `dly.c(...)` (hex).
- Has a device-cache refresh (`BluetoothGatt.refresh()`) and reconnect logic.

**Implication:** Android's GATT layer is a conventional client; the proprietary
work is entirely in the `FE86` payload, not in custom GATT procedures.

## 3. Command transport — `o.djp` (`BTDeviceSendCommandUtil`)

Evidence:

- Holds a command list and a send timeout counter.
- `DeviceCommand` carries service ID, command ID, data, `needEncrypt`, `needAck`.
- `after encryptTLVs & transferV2ToV1, btV1Command` log line shows a V2→V1
  conversion layer for older firmware.
- Uses `dig.e(context, data, mac, key)` for encryption before writing.
- Uses `djm`/`djw` for slicing/reassembly.
- Handles command-specific retries and special cases (`7/2` user info → `7/9`,
  `2/1` message → `2/3`).

**Implication:** the Band 9 may negotiate protocol V2 but the app supports a
V1 fallback. Our client should implement V2 first and only port V1 if the
LinkParams response demands it.

## 4. Handshake and crypto

### `o.dig` (`BTHandshakeManager`)

- Builds the initial handshake with TLVs:
  - `0x01` = 0
  - `0x03` = 6-byte device/bind id
  - `0x04` = 1-byte value `0x02`
  - `0x05` = 0
  - `0x07` = phone MAC (with a fixed fallback `FF:FF:FF:FF:FF:CC`)
  - optional `0x09`
- Wraps the payload with `dic.a(...)`.
- `dig.e(context, data, mac, key)` is the encryption entry point.

### `o.dip` (crypto helpers)

- `a(int, byte[], byte[], byte[])`, `c(int, ...)`: key derivation/encryption.
- `a(byte[])`, `b(byte[], byte[])`: digest/HMAC.
- `a(int)`: nonce/key generation.

### `o.dkc` (HiChain command codec)

- Builds TLVs for HiChain sub-commands (tags `0x28`, `0x2C`, `0x33`, `0x34`).
- Parses TLVs with a 4-hex-char prefix (skips the V1 header).
- Reads status tag `0x7F` and returns codes such as 100000 (`0x000186A0`).
- Handles PIN data and authenticate-type responses.

### `HiChainAuthManager`

- Uses `HwDeviceAuthManager` (`com.huawei.security.deviceauth`).
- `bindPeer` / `authenticatePeer` with `OperationCode.BIND` /
  `AUTHENTICATE`.
- `onDataTransmit` forwards HiChain frames to `o.djp`.
- `onSessionKeyReturned` stores the session key.
- PIN path: `dkc.a()` / `dkc.c()`; if empty, it asks the device (5.1.44).
- `onReceiveRequest` sets a confirmation constant and PIN for
  `BIND`/`AUTH_KEY_AGREEMENT`.

**Implication:** Huawei Health itself does not hand-roll HiChain3 in Java; it
uses Huawei's device-auth SDK. An independent client must reimplement the wire
protocol, not the SDK. Gadgetbridge is the best reference for that.

## 5. Measurement command builders

### FitnessData (`0x07`) — `o.dsw` (`FitnessSendCommandUtil`)

Confirmed builders (APK static):

| ID | Builder | Meaning |
|---|---|---|
| `0x01` | `c(List<MotionGoal>)` | set motion goal |
| `0x02` | `d(UserInfomation)` | set user info |
| `0x03` | `c()` | get today total |
| `0x04/0x05/0x08` | `d/b/d` | health data by frame |
| `0x0A/0x0B` | `c/a` | sample frame count/data |
| `0x0C/0x0D` | `a/c` | status frame count/data |
| `0x0E` | `e(List<dto>)` | report thresholds |
| `0x10` | `a(boolean)` | could-summary enable |
| `0x13` | `c(HeartZoneConf)` | HR zones |
| `0x16` | `e(int)` | core-sleep enable |
| `0x17` | `f(int)` | **automatic HR enable** |
| `0x18` | `k(int)` | sleep state |
| `0x1C` | `h(int)` | **continuous HR enable** |
| `0x1D` | `d(int,int)` | HR high reminder |
| `0x22` | `b(int,int)` | HR low reminder |
| `0x23` | `HwHeartAbility` | resting-HR capability |
| `0x24` | `i(int)` | **cycle/automatic SpO₂ enable** |
| `0x25` | `e(int,int)` | SpO₂ low reminder |
| `0x26` | `b(long,long)` | SpO₂ low count |
| `0x27` | `g(int)` | SpO₂ low detail |
| `0x28` | `h(int)` | (also mapped to continuous HR in some code paths) |

> The exact numeric mapping for every builder should be re-checked in the
> decompiled source before implementation; the table is a navigation aid, not
> a frozen spec.

**Interval result:** `0x17`, `0x1C` and `0x24` carry a one-byte enable/status
value. No interval TLV exists in these builders.

### Heart rate / RRI (`0x19`, `0x20`)

`HwHeartRateManager`:

- `setServiceID(25)` / `setCommandID(1)`:
  - TLV `0x01` len 1 = open/close
  - optional TLV `0x02` len 1 = loudspeaker-mute (productType 11)
- `setServiceID(25)` / `setCommandID(3)`:
  - TLV `0x7F` = status/data response
- `setServiceID(23)` / `setCommandID(15)` and `18`:
  - workout report status / open-close report

`HwHeartAbility`:

- `0x17/0x17`: heart capability, TLV `0x01` len 4 `00000003`
- `0x07/0x23`: new resting-HR capability, TLV `0x01` len 4 `00000001`
- `0x07/0x29`: medium-to-high strength thresholds

`RriHeartRateSendCommandUtil`:

- `0x20/0x09`: stress calibration payload (TLVs 1 = enable, 2 = score,
  3 = 12 floats / 48 bytes, 4 = start time)
- `0x20/0x0A`: stress app-press info (score, start/end time, grade, features)

`HwDevicePeriodRriFileManager`: syncs the `rrisqi_data` file for periodic RRI
and stress data.

### Live HR data rate

The live-HR stream is `0x19/0x03`; the app sends a `0x7F` response. The actual
notification cadence is not visible statically. This is the highest-value
runtime experiment (E03/E07).

## 6. Storage and data dictionary

- Huawei Health uses HiHealth databases and SQLCipher (`libsqlcipher.so`).
- Device metadata and settings live in shared preferences and private DBs.
- The app's `assets/product_map.json` maps `KIM-B19` to HUAWEI Band 9
  (device ids 747–750, 761, 811).
- The app also ships `assets/healthModel/HealthTaskConfig.txt`,
  `SportTypeConfig.json`, sleep tag configs and workout definitions.

The BLE protocol is a better source of truth for measurements than the app DB,
because the app may transform or aggregate values.

## 7. Native libraries of interest

| Library | Likely role |
|---|---|
| `libwhiteBoxJniLib.so` | white-box crypto / protocol helper (mentioned in prior work) |
| `libJniRRI.so`, `libModule_AM16_RRI.so` | RRI/HRV algorithms |
| `libDetailStressJni.so`, `libJanusStressJni.so` | stress algorithms |
| `libDetailSleepJni.so`, `libDetailSleep.so` | sleep staging |
| `libBiofeedBack.so` | biofeedback |
| `libsqlcipher.so` | encrypted local DB |
| `libstep.so`, `libTrackProcess.so` | activity/step processing |

No native reversing is planned until Java/HCI captures are exhausted.

## 8. What the architecture tells us

1. **The app is a conventional BLE central.** No custom GATT; all proprietary
   behaviour is in `FE86` payloads.
2. **Authentication is HiChain.** The app uses Huawei's SDK, so the wire format
   must be reimplemented from Gadgetbridge/Huawhoop, not copied from the app.
3. **The command surface is broad but flat.** `DeviceCommand` is just
   service/command/data; the Band 9 gates support via capability bitmaps.
4. **There is no interval command.** Continuous HR and automatic SpO₂ are
   on/off; cadence is firmware-controlled.
5. **Live HR/RRI exists** (`0x19/0x01`, `0x03`, `0x05`) and is the best hope
   for higher-rate data.
6. **Historical data is service `0x07` and file services** (`0x2C`), matching
   Gadgetbridge.

## 9. Runtime checks completed

- E01/E02 pairing/initialization: captured; HiChain3 confirmed.
- LinkParams: protocol version 1, authVersion 1, deviceSupportType 4.
- AES-GCM TLV encryption confirmed; plaintext recovered.
- `0x07/0x17` automatic HR and `0x07/0x24` automatic SpO₂ confirmed as
  on/off-only.
- Fitness history and file requests observed (`0x07/0x03`, `0x0A`/`0B`,
  `0x0C`/`0D`, `0x2C/0x01`, `0x0F/*`).

Still open: live HR/RRI (`0x19`), historical record field decoding, and the
decision on factory reset to bind an independent HiChain3 key.
