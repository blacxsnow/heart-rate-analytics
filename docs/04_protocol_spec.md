# 04 — Protocol Specification (Working Document)

**Scope:** Huawei Band 9 proprietary `FE86` channel and the standard HRS channel.
**Status:** living document. Every command carries a confidence tag.

Confidence tags:

- **CONFIRMED** — exercised on the physical Band 9, or byte-for-byte matched to
  two independent implementations and checked against the device.
- **LIKELY** — implemented from Gadgetbridge / Huawhoop / the Huawei Health APK
  and consistent with observed traffic, but not yet exercised on this unit.
- **HYPOTHESIS** — inferred; do not claim support.

---

## 1. GATT transport

| Role | UUID | Properties |
|---|---|---|
| Service | `0000fe86-0000-1000-8000-00805f9b34fb` | primary |
| Host → band | `0000fe01-0000-1000-8000-00805f9b34fb` | write / write-no-response |
| Band → host | `0000fe02-0000-1000-8000-00805f9b34fb` | notify (CCCD `2902`) |

The host must enable notifications on `FE02` before sending a request. The band
answers with one or more notifications on `FE02`.

Standard HRS uses `0x180D/0x2A37` and is independent of this channel.

## 2. Frame format

### 2.1 Unsliced frame (CONFIRMED)

```
offset  size  field
0       1     0x5A magic
1       2     length, big-endian: len(service_id + command_id + TLVs) + 1
3       1     slice type: 0x00 = unsliced
4       1     service id
5       1     command id
6       n     TLVs
6+n     2     CRC16-HQXQ over all preceding bytes, big-endian
```

`length` includes the slice byte. Total frame size = `length + 5`.

Example — the documented LinkParams request:

```
5A 00 0B 00 01 01 01 00 02 00 03 00 04 00 F1 3B
│  │     │  │  │  └── TLV 1, len 0
│  │     │  │  └───── command 0x01
│  │     │  └──────── service 0x01 (DeviceConfig)
│  │     └─────────── slice 0
│  └───────────────── length 0x000B
└──────────────────── magic
```

CRC16: `binascii.crc_hqx(data, 0)`; the published CRC for this frame is
`0xF13B`, and `tests/test_protocol.py` asserts it.

### 2.2 Sliced frame (HYPOTHESIS)

Huawhoop documents the large-payload form as:

```
5A LL LL <slice: 1|2|3> <flag> <payload> CRC16
```

- `slice=1` first, `2` middle, `3` last.
- `flag` is a shared counter (0–255, wraps).
- The first slice contains service/command + TLVs; later slices contain TLV
  bytes only.
- Reassembly is implemented in `protocol.FrameDecoder` but has not been
  exercised on this Band 9.

Do not rely on slicing until a large real response is captured.

## 3. TLV encoding (LIKELY / partly CONFIRMED)

```
tag (1 byte) | length (base-128 varint, big-endian) | value
```

- Length `0` is encoded as one byte `00` (Huawei's encoder), not as an empty
  sequence.
- Multi-byte lengths use 7 bits per byte with the high bit set on all but the
  last byte (`128 → 81 00`, `300 → 82 2C`).
- Tags with bit 7 set (`0x80`+) are often nested TLV containers:
  `0x81`, `0x82`, `0x83`, `0x84` are observed in Gadgetbridge/Huawhoop.

The LinkParams request uses four empty TLVs (`01 00 02 00 03 00 04 00`), which
is **CONFIRMED**.

## 4. LinkParams handshake

### 4.1 Request (CONFIRMED)

`service=0x01`, `command=0x01`, TLVs `0x01..0x04` empty.

```
5A 00 0B 00 01 01 01 00 02 00 03 00 04 00 F1 3B
```

This is a read-only handshake. It does not bond or change configuration.

### 4.2 Response (LIKELY)

Gadgetbridge `DeviceConfig.LinkParams.Response` parses:

| TLV | Field | Encoding |
|---|---|---|
| `0x01` | protocol version | uint8 |
| `0x02` | slice size | uint16 BE |
| `0x03` | MTU | uint16 BE |
| `0x04` | connection interval | uint16 BE |
| `0x05` | auth version + server nonce | byte[0]=?, byte[1]=authVersion, bytes[2:18]=nonce |
| `0x07` | device support type | uint8 |
| `0x08` | auth algorithm | uint8 |
| `0x09` | bond state | uint8 |
| `0x0C` | encryption method | uint8 |

`deviceSupportType` selects the auth family:

| Value | Family |
|---|---|
| 1 or 3 | HiChain |
| 2 | HiChain Lite |
| 4 | HiChain3 |
| 0 | no HiChain |

`authVersion` selects the digest secret (v1/v2/v3) and the secret-key derivation.

### 4.3 Device status / security negotiation (LIKELY)

After LinkParams, Gadgetbridge sends:

- `GetDeviceStatusRequest`
- `DeviceConfig.SecurityNegotiation` (`0x01/0x33`) with:
  - `0x01` auth mode (`2` for Lite, `4` for HiChain3)
  - `0x02` = `0x01` for modes 2/4
  - `0x05` Android ID / device UUID
  - `0x03` = `0x01`, `0x04` = `0x00`
  - `0x06` empty, `0x07` phone model (HiChain3)
  - `0x0D` = `0x01` if encryption method 1

The response's `0x01`/`0x02`/`0x7F` yields the auth type
(`0x0186A0`, 1/2, or 5/6).

## 5. Authentication

### 5.1 HiChain Lite (LIKELY for some Band 9 firmware)

Reference: Gadgetbridge `HuaweiCrypto`, `GetAuthRequest`, `GetBondParamsRequest`.

1. Generate/resume a 16-byte `secretKey`.
2. Build `doubleNonce = serverNonce || clientNonce`.
3. `challenge = first 32 bytes of HMAC-based digest`, `firstKey = next 16 bytes`.
4. Send `DeviceConfig.Auth` with the challenge and
   `nonce = authVersion(2 bytes) || clientNonce(16)`.
5. Verify the band's response digest.
6. Exchange bond params (serial, phone MAC), obtain encryption counter.
7. Encrypt subsequent TLVs.

The digest function is version- and mode-dependent:

- `authVersion == 1` → `DIGEST_SECRET_v1`
- `authVersion == 2` → `DIGEST_SECRET_v2`
- `authVersion >= 3` → `DIGEST_SECRET_v3`
- Lite mode (`authMode == 2`) with `authVersion == 2` uses a special
  `secretKey || MESSAGE_CHALLENGE` HMAC.
- Lite mode with other auth versions uses `computeDigestHiChainLite`:
  SHA-256 of the hexdump of the key, XOR with the digest secret, then
  HMAC-SHA256 or PBKDF2-HMAC-SHA256 (1,000 iterations, 256-bit) depending on
  `authAlgo`.

**Do not reimplement from memory.** Port the Java code and add test vectors
from the Android HCI capture.

### 5.2 HiChain / HiChain3 (LIKELY for newer firmware)

- HiChain: PIN/account-based handshake via
  `GetPincodeRequest` + `GetHiChainRequest`.
- HiChain3: `deviceSupportType=4`, `authType=0x05` (Band 10 observation),
  app-side HiChain SDK (`HwDeviceAuthManager`) in Huawei Health.
- If the band is already bound to Huawei Health, the watch may require the
  account-derived key. Gadgetbridge's workaround uses the 17-digit Huawei
  account ID.
- **An independent client cannot assume it can authenticate a band that is
  bound to someone else's account.** A factory reset (with consent) is the
  clean path to bind a new key.

### 5.3 Encryption (LIKELY)

After auth, TLVs may be wrapped in:

- tag `0x01` = encryption flag (`0x01`)
- tag `0x02` = IV (16 bytes)
- tag `0x03` = ciphertext

AES-CBC with PKCS#7 padding, or AES-GCM when `encryptMethod == 0x01`.
The IV counter increments per packet; `deviceSupportType == 4` uses a random
nonce instead of a counter.

## 6. Known / candidate service and command IDs

From Gadgetbridge and Huawhoop. None of the proprietary commands below are yet
confirmed on this Band 9.

| Service | Command | Meaning | Confidence |
|---|---|---|---|
| `0x01` DeviceConfig | `0x01` | LinkParams | **CONFIRMED request** |
| `0x01` | `0x02` | Supported services | LIKELY |
| `0x01` | `0x03` | Supported commands | LIKELY |
| `0x01` | `0x05` | Auth challenge | LIKELY |
| `0x01` | `0x0B` | Bond params | LIKELY |
| `0x01` | `0x33` | Security negotiation | LIKELY |
| `0x01` | `0x35` | Connect status | LIKELY |
| `0x01` | `0x37` | Expand capability | LIKELY |
| `0x07` FitnessData | `0x0A` | Step/minute history | LIKELY |
| `0x07` | `0x0C` | Sleep history | LIKELY |
| `0x07` | `0x17` | Enable automatic HR | LIKELY |
| `0x07` | `0x23` | Notify resting HR capability | LIKELY |
| `0x07` | `0x24` | Enable automatic SpO₂ | LIKELY |
| `0x19` Workout/Health | `0x01` | Live HR / RRI request (`hr_type`) | HYPOTHESIS (Band 10) |
| `0x19` | `0x03` | Real-time HR notifications | HYPOTHESIS (Band 10) |
| `0x19` | `0x05` | RRI/SQI notifications | HYPOTHESIS (Band 10) |
| `0x19` | `0x17` | Notify HR capability | LIKELY |
| `0x2C` FileDownload | — | TruSleep / sequence data | LIKELY |

### 6.1 Interval control

- Standard HRS is fixed at ~1 Hz. There is no standard way to request a faster
  rate; the band's PPG sampling and notification cadence are firmware-controlled.
- Huawei Health 11.0.0.517's own command surface (static analysis) contains
  **only on/off or mode bytes** for continuous HR and automatic SpO₂:
  - `0x07/0x17` `sendSetHeartRateEnableCmd`: TLV `0x01` = 1 byte enable.
  - `0x07/0x1C` `sendSetContinueMeasureHeartRateEnableCmd`: TLV `0x01` = 1 byte
    status (continuous measurement).
  - `0x07/0x24` `sendCycleBloodOxygenEnableCmd`: TLV `0x01` = 1 byte status
    (cycle/automatic SpO₂).
  - `0x07/0x1D` and `0x07/0x22` are HR/SpO₂ reminder thresholds, not sampling
    intervals.
- No TLV carrying a measurement interval (seconds/minutes) was found in these
  command builders. The UI's "Smart vs Real-time" choice selects a mode, not a
  numeric cadence.
- Huawhoop's Band 10 live-HR command (`0x19/0x01`) is a separate real-time
  stream; its rate is also not proven configurable.
- Conclusion: **"aggressive configurable intervals" is not supported by any
  known public implementation and is not present in Huawei Health's command
  builders.** The cadence appears firmware-controlled. Treat any higher-rate
  claim as unverified until a command with an interval parameter is captured.

### 6.2 Additional commands confirmed in the Huawei Health APK

These are **APK-CONFIRMED** (found in the exact installed 11.0.0.517 code) but
**not yet verified on the physical Band 9**. Service IDs are decimal in the
Java source; values below are hex.

| Service | Command | Java builder | Meaning |
|---|---|---|---|
| `0x07` | `0x01` | `dsw.c(List<MotionGoal>)` | set motion goal |
| `0x07` | `0x02` | `dsw.d(UserInfomation)` | set user info |
| `0x07` | `0x03` | `dsw.c()` | get today total |
| `0x07` | `0x04/0x05/0x08` | `dsw.d/b/d` | health data by frame/count |
| `0x07` | `0x0A/0x0B` | `dsw.c/a` | sample frame count/data |
| `0x07` | `0x0C/0x0D` | `dsw.a/c` | status frame count/data |
| `0x07` | `0x0E` | `dsw.e(List<dto>)` | device report threshold |
| `0x07` | `0x10` | `dsw.a(boolean)` | could-summary enable |
| `0x07` | `0x13` | `dsw.c(HeartZoneConf)` | HR zone config |
| `0x07` | `0x15` | `dsw.e()` | ? |
| `0x07` | `0x16` | `dsw.e(int)` | TruSleep/core-sleep enable |
| `0x07` | `0x17` | `dsw.f(int)` | **heart-rate enable** |
| `0x07` | `0x18` | `dsw.k(int)` | sleep state |
| `0x07` | `0x19` | `dsw.o(int)` | ? |
| `0x07` | `0x1A` | `dsw.l(int)` | ? |
| `0x07` | `0x1C` | `dsw.h(int)` | **continuous HR enable** |
| `0x07` | `0x1D` | `dsw.d(int,int)` | HR high reminder |
| `0x07` | `0x21` | `dsw.e()` | ? |
| `0x07` | `0x22` | `dsw.b(int,int)` | HR low reminder |
| `0x07` | `0x23` | `HwHeartAbility` | new resting-HR capability |
| `0x07` | `0x24` | `dsw.i(int)` | **cycle/automatic SpO₂ enable** |
| `0x07` | `0x25` | `dsw.e(int,int)` | SpO₂ low reminder |
| `0x07` | `0x26` | `dsw.b(long,long)` | SpO₂ low count |
| `0x07` | `0x27` | `dsw.g(int)` | SpO₂ low detail |
| `0x07` | `0x1F` | `dsw.a(long,long,int)` | ? |
| `0x07` | `0x20` | `dsw.p(int)` | ? |
| `0x17` | `0x0F` | `HwHeartRateManager` | workout report status |
| `0x17` | `0x12` | `HwHeartRateManager` | open/close report |
| `0x17` | `0x17` | `HwHeartAbility` | heart capability |
| `0x19` | `0x01` | `HwHeartRateManager` | **live HR on/off** (TLV 1=1/0, optional TLV 2) |
| `0x19` | `0x03` | `HwHeartRateManager` | **live HR data/response** (TLV 0x7F) |
| `0x19` | `0x05` | Huawhoop | RRI/SQI stream (Band 10 evidence) |
| `0x20` | `0x09` | `RriHeartRateSendCommandUtil` | stress calibration payload |
| `0x20` | `0x0A` | `RriHeartRateSendCommandUtil` | stress app-press info |

The live-HR request builder is approximately:

```
service 0x19, command 0x01
TLV 0x01, len 1, value = enable (1) / disable (0)
TLV 0x02, len 1, value = loudspeaker-mute status   (only for productType 11)
```

The live-HR data path is `0x19/0x03`; Huawhoop's Band 10 work additionally
reports RRI/SQI on `0x19/0x05` for `hr_type=3`. A `0x19/0x03` packet carries a
`0x7F` status/data TLV. These need hardware verification on the Band 9.


## 7. Standard HRS channel (CONFIRMED)

- Service `0x180D`, characteristic `0x2A37`, notify.
- One notification per second.
- Flags `0x06`: uint8 HR, contact supported + detected.
- No energy expended, no RR intervals.
- The stream is started by **Settings → HR Data Broadcasts** on the band, not by
  a BLE command. It survives display-off and host disconnect (verified).
- `0x2A38` = `0x02` (wrist).
- `0x2A39` is writable but was not used.

## 8. Android-reference hypotheses to test

The exact Huawei Health APK (11.0.0.517) contains:

- `o/djr.java` — GATT client for `FE86/FE01/FE02`, with a 0x200/0x203/0x202
  fallback for older devices, notification setup, write queue, and reconnect.
- `com/huawei/hwbtsdk/hichain/HiChainAuthManager.java` — app-side HiChain
  bind/authenticate wrapper, session-key callback, PIN handling.
- `o/dkc.java` — HiChain command TLV builder/parser (`0x28`, `0x2C`, `0x33`
  etc. in HiChain sub-protocol).
- `o/djp.java` — command queue, V1/V2 conversion, encryption, slicing and
  reassembly.
- `o/dig.java` — handshake packet builder and encryption wrapper.
- `o/dip.java` — AES/HMAC helpers.

These classes give us the exact app-side sequence to compare with HCI captures.

## 9. On-device confirmed capture (2026-11-25)

A rooted-phone capture with Frida (GATT + `javax.crypto.Cipher`) produced a
complete HiChain3 session and decrypted FE86 commands. Values below are
sanitised; per-session keys, MACs and personal data are not published.

### 9.1 LinkParams response (CONFIRMED)

Request: `5A 00 0B 00 01 01 01 00 02 00 03 00 04 00 F1 3B`

Response (TLVs decoded):

| Field | Value | Meaning |
|---|---|---|
| `0x01` | `01` | protocol version 1 |
| `0x02` | `00 F4` | slice size 244 |
| `0x03` | `00 F4` | MTU 244 |
| `0x04` | `00 00` | connection interval field 0 |
| `0x05` | `00 01 <16-byte nonce>` | auth version **1**, server nonce |
| `0x07` | `04` | device support type **4 = HiChain3** |
| `0x09` | `00` | bond state 0 |
| `0x0D` | `00` | encryption method 0 |

This is the first hardware confirmation that this Band 9 uses **HiChain3**
(`authMode=4`), not HiChain Lite.

### 9.2 Security negotiation (CONFIRMED)

`0x01/0x33` request TLVs:

```
0x01 = 04                       auth mode 4 (HiChain3)
0x02 = 01
0x05 = <16-byte Android ID>     (redacted)
0x03 = 01
0x04 = 00
0x06 = "phoneIdentify"
0x07 = "OnePlus 11R 5G"
```

The response contains a 64-ASCII-hex `peerAuthId`, an 18-byte zero field, and
the band's own peer-auth ID/address (redacted).

### 9.3 HiChain3 JSON handshake (CONFIRMED)

The auth exchange is carried in `0x01/0x28` packets whose payload is a JSON
object (not ordinary TLVs), split across LP frames:

```
{"authForm":0,"payload":{"isoSalt":"<32 hex>","token":"<64 hex>",
 "peerAuthId":"<64 hex>", "peerUserType":0, "operationCode":2,
 "version":{"minVersion":"1.0.0","currentVersion":"2.0.16"}},
 "message":32785,"groupAndModuleVersion":"2.0.1","isDeviceLevel":false}
```

The app answers with its own `peerAuthId`, then a `nonce` + `encResult`,
and the band returns a `returnCodeMac`. The final `0x01/0x28` packet carries
`"com.huawei.health"` and status TLV `0x7F = 0x000186A0` (100000 = success).

**Implication:** independent auth requires reproducing HiChain3 JSON steps and
the account-bound long-term key; this is not a simple password. The handshake
is now fully captured for implementation.

### 9.4 TLV encryption (CONFIRMED)

Encrypted payloads use:

```
0x7C len 1 value 01          encryption flag
0x7D len 16 value <IV>       GCM IV
0x7E len n value <ciphertext || 16-byte tag>
```

- **AES-GCM**, not AES-CBC, for this session.
- A 16-byte tag is appended to the ciphertext.
- The key is per-session and was observed in the app's `SecretKeySpec`.
  The key is **not** published here.
- Decryption was verified by matching each FE01 ciphertext to the app's
  `Cipher.doFinal` input and obtaining valid TLVs.

### 9.5 Confirmed command map

| Service/command | Direction | Plaintext example | Meaning | Status |
|---|---|---|---|---|
| `0x07/0x17` | tx | `01 01 01` / `01 01 00` | automatic/continuous HR **on/off** | **CONFIRMED** |
| `0x07/0x24` | tx | `01 01 01` / `01 01 00` | automatic SpO₂ **on/off** | **CONFIRMED** |
| `0x07/0x25` | tx | `01 01 01 02 01 5A` | SpO₂ low alert threshold (0x5A=90%) | **CONFIRMED** |
| `0x07/0x1D` | tx | `01 01 01 02 01 78` | HR high alert threshold (120 bpm) | **CONFIRMED** |
| `0x07/0x22` | tx | `01 01 01 02 01 28` | HR low alert threshold (40 bpm) | **CONFIRMED** |
| `0x07/0x03` | tx | `01 00` | get today total | **CONFIRMED** |
| `0x07/0x0A` | tx | `81 00 03 04 <start> 04 04 <end>` | sample frame count | **CONFIRMED** |
| `0x07/0x0B` | rx | `81 ...` | sample frame data (minute records) | **CONFIRMED** |
| `0x07/0x0C` | tx | `81 00 03 04 <start> 04 04 <end>` | status frame count | **CONFIRMED** |
| `0x07/0x0D` | rx | `81 ...` | status frame data | **CONFIRMED** |
| `0x07/0x1E` | tx | `01 04 <time> 02 04 <time> 0D 01 00/01` | likely stress/SpO₂ data window | LIKELY |
| `0x07/0x1F` | tx | `02 04 <time> 03 04 <time> 04 01 00` | likely data window | LIKELY |
| `0x07/0x26` | tx | `01 04 <time> 02 04 <time>` | likely data window | LIKELY |
| `0x2C/0x01` | tx | `01 0D "sequence_data" 02 01 16 05 04 <start> 06 04 <end> 0C 04 <...>` | request sleep/sequence file | **CONFIRMED** |
| `0x2C/0x01` | rx | `... 7F 04 00 02 32 81` | no new file (`0x00023281`) | **CONFIRMED** |
| `0x0F/0x01`–`0x0F/0x0A` | both | file-transfer TLVs | OTA/file service | **CONFIRMED transport, semantics partial** |
| `0x27/0x01` | both | version/capability TLVs | device version/capability | **CONFIRMED** |
| `0x34/0x01` | both | app IDs (`hw.unitedevice.track`, `in.huawei.fitness`, ...) | P2P service registry | **CONFIRMED** |
| `0x37/0x03` / `0x37/0x02` | both | sport config / dictionary sync | data dictionary | **CONFIRMED** |

### 9.6 Device identity (CONFIRMED)

The authenticated `0x27/0x01` device-info response contains a JSON constants
object. Sanitised fields:

| Field | Value |
|---|---|
| `DT` (device type) | `Kimi-B19FB` |
| `DV` (firmware) | `4.2.0.230(C00M07)` |
| `HEALTH_MODEL` | `THREECIRCLECARD` |
| `CC` (country) | `GB` |
| `DID` (unique device id) | **redacted** |
| `MANUFACTURER` | OnePlus (phone side) |

This is the authoritative firmware/model source. The standard DIS remains
useless (`HUAWEI` / `1.0.0.1`).

### 9.7 Interval conclusion (CONFIRMED on device)

The settings toggle experiment produced:

```
automatic HR off:   0x07/0x17  -> 01 01 00
automatic HR on:    0x07/0x17  -> 01 01 01
automatic SpO2 off: 0x07/0x24  -> 01 01 00
automatic SpO2 on:  0x07/0x24  -> 01 01 01
```

There is **no interval field** in either command. The only numeric fields in
the surrounding commands are alert thresholds (`0x1D`, `0x22`, `0x25`), not
sampling periods. Aggressive/configurable intervals are therefore **not
available through Huawei Health's command surface** and are almost certainly
firmware-controlled.

## 10. Open questions


1. Which auth family does this firmware report?
2. Is the unit already bound to an account, and does that block an independent
   key?
3. Does `0x19/0x01` exist on Band 9, and at what rate?
4. Are automatic HR/SpO₂ intervals configurable via hidden TLVs?
5. Is SpO₂ available live, or only as historical samples?
6. Does the Band 9 expose RRI for HRV?
7. What do the vendor services `3802`, `E2CB`, `E2E3`, `CC353442` do?
