# 16 — HiChain3 and Physiological Streams (Track B, offline phase)

**Constraint for this phase:** no phone UI automation and no band interaction.
Everything below is from existing captures, the installed APK/decompile, and the
firmware images. Items that still require the device are marked **UNVERIFIED**.

---

## 1. What is already confirmed

### 1.1 Transport and LinkParams

The proprietary channel is GATT service `FE86` (`FE01` write, `FE02` notify).
The read-only LinkParams handshake is confirmed on this Band 9:

```
request : 5A 00 0B 00 01 01 01 00 02 00 03 00 04 00 F1 3B
response: 0x01 protocol 1
          0x02 slice size 244
          0x03 MTU 244
          0x04 connection interval field 0
          0x05 00 01 <16-byte server nonce>   (auth version 1)
          0x07 04                             (deviceSupportType = HiChain3)
          0x09 00                             (bond state 0)
          0x0D 00                             (encryption method 0)
```

### 1.2 Security negotiation

`0x01/0x33` carries:

```
0x01 = 04                       auth mode 4 (HiChain3)
0x02 = 01
0x05 = <16-byte phone identifier>
0x03 = 01
0x04 = 00
0x06 = "phoneIdentify"
0x07 = <phone model>
```

The response contains a 64-ASCII-hex `peerAuthId`, an 18-byte zero field, and
the band’s own peer-auth identity.

### 1.3 HiChain3 JSON handshake

Carried in `0x01/0x28` frames as JSON, not ordinary TLVs:

```json
{"authForm":0,
 "payload":{"isoSalt":"<32 hex>","token":"<64 hex>",
            "peerAuthId":"<64 hex>","peerUserType":0,
            "operationCode":2,
            "version":{"minVersion":"1.0.0","currentVersion":"2.0.16"}},
 "message":32785,
 "groupAndModuleVersion":"2.0.1",
 "isDeviceLevel":false}
```

The app answers with its own `peerAuthId`, a `nonce` + `encResult`, and the band
returns a `returnCodeMac`. Success is signalled by status TLV
`0x7F = 0x000186A0` (100000).

### 1.4 Post-auth encryption

Encrypted TLV blocks use AES-GCM:

```
0x7C len 1  value 01               encryption flag
0x7D len 16 value <IV>
0x7E len n  value <ciphertext||16-byte tag>
```

The key is per-session and was observed in the app’s `SecretKeySpec`. It is not
published. This envelope is implemented offline in
`src/fitness_band/proprietary.py`.

### 1.5 Confirmed live capture (2026-11-25, 21:45)

A fresh GATT + AES-GCM capture on `:PhoneService` recorded the whole exchange.
The auth JSON messages are plaintext (not yet inside the GCM envelope):

| # | Direction | `message` | Payload fields |
|---|---:|---:|---|
| 1 | app → band | 17 | `isoSalt`, `peerAuthId`, `operationCode=2`, `seed`, `peerUserType`, `pkgName`, `serviceType`, `keyLength=32` |
| 2 | band → app | 32785 | `isoSalt`, `token`, `peerAuthId`, `peerUserType`, `operationCode=2` |
| 3 | app → band | 18 | `peerAuthId`, `token` |
| 4 | band → app | 32786 | `peerAuthId`, `returnCodeMac` |
| 5 | app → band | 19 | `nonce`, `encResult`, `operationCode=2` |
| 6 | band → app | — | service string `com.huawei.health` |

After message 6, both directions use the AES-GCM envelope. The live capture
yielded a **32-byte** per-session key, used for 500 GCM operations; the key is
stored only in the local/gitignored capture, never in the repository.

**Sliced-frame detail (corrected):** fragments carry a one-byte sequence marker
(`00` on the first, then `01`, `02`, …). Stripping every fragment marker is
required; otherwise a stray `0x01`/`0x02` appears inside the JSON. The frame
decoder and its tests now implement this.

## 1.6 Confirmed post-auth command stream

Opening the device page and Health monitoring produced, in order:

| Service/command | Direction | Decoded payload | Interpretation |
|---|---|---|---|
| `0x27/0x01` | both | capability list, version `2.3` | device info |
| `0x27/0x02` | both | long capability/command list | supported commands |
| `0x07/0x03` | tx | `01 00` | today totals |
| `0x07/0x0A` | tx | `81 00 03 04 <start> 04 04 <end>` | HR sample-window request |
| `0x07/0x0B` | rx | `81 <len>` array | HR minute records |
| `0x07/0x0C` | tx | same window shape | status-window request |
| `0x07/0x0D` | rx | `81 <len>` array of `0x83` records | status records |
| `0x07/0x17` | tx | `01 01 01` | automatic HR on |
| `0x07/0x24` | tx | `01 01 01` | automatic SpO₂ on |
| `0x07/0x1F` | tx | `02 04 <start> 03 04 <end> 04 01 00` | SpO₂ window; reply `01 02 0000` |
| `0x07/0x1E` | tx | `01 04 <start> 02 04 <end> 0D 01 00/01` | SpO₂ status/window |
| `0x07/0x26` | tx | `01 04 <start> 02 04 <end>` | SpO₂ window; reply `03 02 0000` |
| `0x2C/0x01` | tx | `rrisqi_data.bin` | RRI/SQI file request; reply `0x00023281` (no file) |
| `0x2C/0x01` | tx | `sequence_data` | sequence file; no file |
| `0x34/0x01` | both | app IDs (`hw.unitedevice.track`, …) | P2P registry |
| `0x37/0x01`–`0x37/0x03` | both | app/dictionary sync | sport/dictionary P2P |

The time fields in the `0x07` windows are Unix seconds (`0x6B07081C` =
2026-11-25 16:18:12 UTC). The HR batch envelope is:

```
81 <len>
  02 02 0000                 status/type
  03 04 <start timestamp>
  84 <len>                   one minute record
     05 01 <minute index>
     06 <len> <payload>
     [07 ...] [08 ...]
  84 <len> ...
  08 01 00                   trailer
```

`src/fitness_band/history.py` parses this envelope and preserves the inner
`0x06`/`0x07`/`0x08` payloads as raw TLVs; their meaning (HR, SpO₂, steps, …)
is only partially decoded. The status batch (`0x0D`) has the same idea but
uses `0x83` records.

### 1.7 RRI/SQI file transfer (CONFIRMED)

After the band’s Heart-rate screen was used, the app requested
`rrisqi_data.bin` and this time the band returned a file:

```
0x2C/0x01  request  "rrisqi_data.bin", window
0x2C/0x01  reply    file size 0x00000072 (114 bytes)
0x2C/0x03  request  file metadata
0x2C/0x03  reply    file id 0x10, metadata
0x2C/0x04  request  read offset 0, length 0x72
0x2C/0x05  reply    120 bytes (file payload)
0x2C/0x06  request  close
0x2C/0x06  reply    success
```

The 114-byte payload is preserved locally. Its float-like fields are **not**
yet mapped to documented HRV metrics, so the values must not be published or
interpreted as SDNN/RMSSD/etc. The important result is that **RRI/SQI data is
retrievable through `0x2C`** once the band has produced it.

### 1.8 SpO₂ spot measurement — negative result

A spot SpO₂ measurement was performed on the band and displayed **98–99%**
(user-confirmed). The phone-side sync still returned **no records** for
`0x07/0x1E`, `0x07/0x1F` and `0x07/0x26` (all zero statuses).

During the measurement window, service `0x25` exchanged
`0x25/0x03 -> 01 01 64` (`100`). Because the band displayed 98–99%, this value
is **not** the SpO₂ reading and must not be mapped to SpO₂.

A second measurement was then captured live with the value **97%** (and HR
**85 bpm**). The phone transmitted only a periodic `0x25/0x01` poll; there was
**no** `0x25/0x03` value and no live SpO₂ packet. Conclusion: the spot SpO₂
result is **not streamed to the phone**; it is stored on the band.

### 1.9 Band file retrieval (`0x2C`)

Using the already-authenticated GATT session, a `0x2C/0x01` request for
`spo2.bin` returned a real file:

```
file id   0x10
size      0x000021F6 = 8,694 bytes
```

The file was read in 960-byte chunks with `0x2C/0x04` and assembled from
`0x2C/0x05` replies. Chunk format:

```
byte 0      file id
bytes 1-4   offset (big-endian)
byte 5      flag/reserved
bytes 6..   data
```

The complete 8,694-byte file was recovered (local only). Its records carry
timestamps from **17–18 Nov 2026**, not the 25 Nov spot measurement, and its
float fields look like PPG/OSA features rather than a simple SpO₂ percentage.
Requests for `spo2_data_sleep.bin`, `osa_spo2_data.bin`,
`heartrate_data_sleep.bin` and `hrm_historydata.bin` all returned the same
file id/size when sent with selector `0x02 = 0x10`, so the filename is not the
selector; the numeric file id is.

The spot SpO₂ value 97% is therefore still **not located** in a decoded
protocol payload. It may be in a different file id or an on-device database
that the app has not requested in our captures.

**Method note:** injecting a second Frida script that hooked
`onCharacteristicChanged` crashed `:PhoneService` (JNI error). Write-only
injection into the existing `BluetoothGatt` is stable; use
`scripts/frida_write_fe86.js` and let the separate capture observer log the
notifications.

## 2. Band-side confirmation

The XIP firmware image contains the matching HiChain3/HKS implementation (see
`15_firmware_static_analysis.md` §4):

- `hichain_iso_exchange`, `hichain_iso_session_key`, `hichain_iso_result`,
  `hichain_return_key`, `HichainThread`
- `HksServiceInitialize/Encrypt/Decrypt/DeleteKey/KeyExist/ImportKey/DeriveKey`
- `/user/deviceauth/hcgroup.dat`, `%s/hcgroup%d.dat`, `/user/deviceauth`
- JSON keys `authForm`, `peerAuthId`, `isoSalt`, `returnCodeMac`,
  `operationCode`, `groupAndModuleVersion`, `peerUserType`

Interpretation: the band is the HiChain server/peer; long-term group material
is stored in HKS-backed files under `/user/deviceauth`, not in the OTA package.
An independent client cannot derive that material from the firmware images.

## 3. App-side static picture

The base APK (11.0.0.517) contains:

- `com.huawei.hwbtsdk.hichain.HiChainAuthManager` — wrapper around the platform
  HiChain SDK (`bindPeer`, `authenticatePeer`, `onOperationFinished`,
  `onReceiveRequest`).
- `com.huawei.hwbtsdk.btmanager...` and `EncryptData` — transport/encryption
  plumbing.

The base APK does **not** contain the runtime OTA classes `mkl`/`mkp`/`kka`,
and it does not contain the HiChain3 JSON vocabulary. The installed app loads
device/BLE logic dynamically (`PluginWearAbility`, `PluginHealthModel`,
`PluginHiAiEngine`), and the HiChain3 JSON itself is produced by the Huawei
HiChain SDK/plugin, not by the readable base APK. The inspected
`PluginWearAbility` APK contains no plaintext `LinkParams`/`hichain` protocol
strings; the relevant code is further obfuscated, native, or in an HMS module.

**Consequence:** static app analysis gives the shape of the auth flow, but the
exact HiChain3 cryptography is not readable from the base APK alone.

## 4. Capture log from 2026-11-25 21:35 — negative result

A low-overhead Frida observer was attached to a freshly spawned Huawei Health
process and logged AES-GCM operations. It captured a GCM key and plaintext JSON
(`{"_constants":...}`, `{"_activity_name":"CardDeviceFragment"}`), but:

- **zero** GATT writes/notifications were logged;
- the app never reached the BLE session (it ANR’d during startup);
- the GCM payloads are application/analytics JSON, not FE86 TLVs.

Therefore this log is **not** a band traffic capture and is not used as protocol
evidence. It does confirm that GCM is used for app-level payloads too, which is
why a crypto-only observer is ambiguous without GATT correlation.

## 5. Measurement command map and gaps

| Stream | Command | Status |
|---|---|---|
| Heart rate (standard) | GATT `0x180D/0x2A37` | **CONFIRMED**, 1 Hz, uint8, contact bit |
| Automatic HR | `0x07/0x17` TLV `01 01/00` | **CONFIRMED** on/off |
| Automatic SpO₂ | `0x07/0x24` TLV `01 01/00` | **CONFIRMED** on/off |
| HR high/low alert | `0x07/0x1D`, `0x07/0x22` | **CONFIRMED** |
| SpO₂ low alert | `0x07/0x25` | **CONFIRMED** |
| Today total | `0x07/0x03` | **CONFIRMED** |
| HR history count/data | `0x07/0x0A` / `0x07/0x0B` | **CONFIRMED** request/response + envelope; inner fields partial |
| Status history | `0x07/0x0C` / `0x07/0x0D` | **CONFIRMED** request/response + envelope |
| Live proprietary HR | `0x19/0x03` + `0x7F` TLV | **HYPOTHESIS** (Band 10 report; not decoded on Band 9) |
| SpO₂ spot measurement | unknown | **PARTIAL**: band displayed 97% (and 98–99% earlier, user-confirmed); no protocol value captured |
| SpO₂ history/window | `0x07/0x1E`, `0x07/0x1F`, `0x07/0x26` | **PARTIAL**: queries confirmed; no records returned after either spot measurement |
| `spo2.bin` file | `0x2C/0x01/04/05` | **PARTIAL**: 8,694-byte file retrieved; records dated 17–18 Nov, not the spot reading |
| `0x25/0x03` | `01 01 64` | **UNKNOWN**; value 100 is *not* SpO₂ (band showed 97% / 98–99%) |
| IBI / RRI / HRV | `0x2C/0x01` `rrisqi_data.bin`; `0x19/0x05` | **PARTIAL**: 114-byte RRI/SQI file retrieved; HRV tab exists; fields not mapped |
| Raw PPG | unknown | **UNKNOWN**; device stores arrhythmia/OSA PPG files, no external path decoded |
| Sleep/RRI files | `0x2C/0x01` file request | **CONFIRMED** request shape; no new file returned in the capture |

The machine-readable matrix is `capabilities/matrix.yaml`; it distinguishes
“confirmed”, “partial”, “hypothesis”, and “unknown”, and explicitly forbids
inferring IBI/HRV or raw PPG from BPM data.

## 6. Feasibility of independent authentication

Four options, in order of practicality:

1. **Reuse the account-bound group key** — the band stores `hcgroup.dat` in
   `/user/deviceauth`; the OTA image does not contain it. Requires filesystem or
   debug access to the band (sealed, no recovery path). Not available now.
2. **Create a new HiChain3 bind** — if the band accepts a second peer, an
   independent client can perform a bind and derive its own group key. This is
   the most promising non-destructive path, but it is unverified and may require
   removing the phone’s pairing or a factory reset.
3. **Relay through an authorized phone** — phone ↔ proxy ↔ band preserves the
   real HiChain3 session and lets us capture authenticated HR/SpO₂/history.
   Best for protocol validation, but needs the phone and a BLE proxy.
4. **Factory reset and bind only the client** — destructive to the current
   account binding; requires explicit consent and a recovery plan.

Until one of these is exercised, the independent client should not claim
authenticated proprietary streams. Standard HRS remains the only verified
real-time path.

## 7. Next experiments (when the device is free)

1. Start a **spot SpO₂ measurement on the band**, then reopen the device page
   and capture `0x07/0x1E`/`0x1F`/`0x26` with data present.
2. Decode the `0x84`/`0x06` minute payloads into HR/SpO₂/steps by correlating
   the displayed Health graph values with raw records.
3. Open the in-app **HRV** tab and verify whether it triggers a new
   `rrisqi_data.bin` request or only uses cached data.
4. Decode `0x19/0x03` live HR and compare with HRS.
5. Request `hrm_historydata.bin`, `spo2.bin`, `spo2_data_sleep.bin`,
   `osa_spo2_data.bin`, and `arrhythmia_ppg_localdata_new.bin` through `0x2C`.
6. Test `0x19/0x05` for RRI/IBI and record whether the Band 9 answers at all.
7. Capture a complete HiChain3 bind from a second client and check whether the
   band permits it.

## 8. Offline deliverables in this phase

- `src/fitness_band/proprietary.py` — GCM envelope, confirmed command builders,
  security-negotiation request.
- `src/fitness_band/capabilities.py` + `capabilities/matrix.yaml` — validated
  capability matrix.
- `tests/test_proprietary.py`, `tests/test_capabilities.py`,
  `tests/test_history.py` — offline tests.
- `scripts/frida_trackb_capture.js` — low-overhead GATT + AES-GCM observer.
- `scripts/decode_trackb.py` — reassemble, decrypt and dump a capture as JSONL.
- `src/fitness_band/history.py` — partial decoder for `0x07/0x0B` and `0x0D`.
- `15_firmware_static_analysis.md` — architecture evidence.
