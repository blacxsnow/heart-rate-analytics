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
| HR history count/data | `0x07/0x0A` / `0x07/0x0B` | **CONFIRMED** request/response; record fields partial |
| Status history | `0x07/0x0C` / `0x07/0x0D` | **CONFIRMED** request/response |
| Live proprietary HR | `0x19/0x03` + `0x7F` TLV | **HYPOTHESIS** (Band 10 report; not decoded on Band 9) |
| SpO₂ spot measurement | unknown | **UNKNOWN**; candidates `0x07/0x1E`, `0x07/0x26` |
| SpO₂ history | unknown | **HYPOTHESIS**; device files exist |
| IBI / RRI / HRV | `0x19/0x05` | **HYPOTHESIS** (Band 10 only) |
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

1. Capture a complete HiChain3 bind from a second client and check whether the
   band permits it.
2. Decode `0x19/0x03` live HR and compare with HRS.
3. Probe `0x07/0x1E`, `0x07/0x1F`, `0x07/0x26` windows for SpO₂.
4. Decode `0x07/0x0B` minute records into HR/SpO₂/steps.
5. Request `hrm_historydata.bin`, `spo2.bin`, `spo2_data_sleep.bin`,
   `osa_spo2_data.bin`, and `arrhythmia_ppg_localdata_new.bin` through `0x2C`.
6. Test `0x19/0x05` for RRI/IBI and record whether the Band 9 answers at all.

## 8. Offline deliverables in this phase

- `src/fitness_band/proprietary.py` — GCM envelope, confirmed command builders,
  security-negotiation request.
- `src/fitness_band/capabilities.py` + `capabilities/matrix.yaml` — validated
  capability matrix.
- `tests/test_proprietary.py`, `tests/test_capabilities.py` — offline tests.
- `scripts/frida_trackb_capture.js` — low-overhead GATT + AES-GCM observer for
  the next device session.
- `15_firmware_static_analysis.md` — architecture evidence.
