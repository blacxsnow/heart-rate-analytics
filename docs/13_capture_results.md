# 13 — Android Reference Capture Results

**Session:** 2026-11-25, Huawei Health 11.0.0.517 on rooted OnePlus 11R
(Android 16), Frida 17.27.5.
**Device:** Huawei Band 9 (`KIM-B19`), normal FE86 endpoint.
**Artifacts:** GATT/Frida logs, btsnoop and APK remain local and gitignored.
**Sanitisation:** no MAC, account ID, auth key, serial or personal measurement
is reproduced in this document.

---

## 0. Device identity from the capture

| Field | Value |
|---|---|
| Device type string | `Kimi-B19FB` |
| Firmware | `4.2.0.230(C00M07)` |
| Health model label | `THREECIRCLECARD` |
| Country code | `GB` |
| Unique device ID | **redacted** |
| Phone model | OnePlus 11R 5G |

These came from the authenticated proprietary device-info payload
(`0x27/0x01`), not from the placeholder DIS. The firmware is newer than the
`3.1.0.31` discussed in Gadgetbridge issue #3784 and is consistent with the
HiChain3 auth family.

## 1. What was captured

A full reconnect plus device-page sync produced:

- BLE connection and GATT service discovery.
- The plaintext LinkParams handshake.
- Security negotiation selecting **HiChain3**.
- The HiChain3 JSON exchange.
- Encrypted FE86 traffic.
- A settings toggle experiment (automatic HR and automatic SpO₂).
- Fitness-history sync and file requests.

## 2. Authentication

### LinkParams response

| Field | Value |
|---|---|
| Protocol version | 1 |
| Slice size | 244 |
| MTU | 244 |
| Auth version | **1** |
| Device support type | **4 (HiChain3)** |
| Bond state | 0 |
| Encryption method | 0 |

### Security negotiation

Auth mode `4`, Android ID, `phoneIdentify`, phone model. The response carries
the band's peer-auth ID/address (redacted) and a 64-ASCII-hex identifier.

### HiChain3 JSON exchange

Captured fields include:

```
authForm=0
isoSalt=<32 hex>
token=<64 hex>
peerAuthId=<64 hex>
operationCode=2
version={minVersion:"1.0.0", currentVersion:"2.0.16"}
message=32785
groupAndModuleVersion="2.0.1"
isDeviceLevel=false
```

A `returnCodeMac` is returned by the band, followed by a final
`com.huawei.health` packet with status `0x000186A0` (success).

**Conclusion:** independent authentication is feasible only by reproducing
HiChain3 and possessing the account-bound long-term key (or by factory-resetting
the band to bind a new key). This is the main remaining implementation gap.

## 3. TLV encryption

```
0x7C 01 01           encryption flag
0x7D 10 <16 bytes>   GCM IV
0x7E nn <ct||tag>    AES-GCM ciphertext + 16-byte tag
```

- AES-GCM, per-session key.
- The key was observed in the app's `SecretKeySpec` and is not published.
- Plaintext was recovered by matching each FE86 ciphertext to the app's
  `Cipher.doFinal` event.

## 4. Confirmed commands

| Command | Plaintext | Meaning |
|---|---|---|
| `0x07/0x17` | `01 01 01` / `01 01 00` | automatic/continuous HR on/off |
| `0x07/0x24` | `01 01 01` / `01 01 00` | automatic SpO₂ on/off |
| `0x07/0x1D` | `01 01 01 02 01 78` | HR high alert (120 bpm) |
| `0x07/0x22` | `01 01 01 02 01 28` | HR low alert (40 bpm) |
| `0x07/0x25` | `01 01 01 02 01 5A` | SpO₂ low alert (90%) |
| `0x07/0x03` | `01 00` | get today total |
| `0x07/0x0A` | `81 00 03 04 <start> 04 04 <end>` | sample frame count |
| `0x07/0x0B` | `81 ...` | sample/minute data |
| `0x07/0x0C` | `81 00 03 04 <start> 04 04 <end>` | status frame count |
| `0x07/0x0D` | `81 ...` | status data |
| `0x2C/0x01` | `01 0D "sequence_data" ...` | request sleep/sequence file |
| `0x0F/0x01`–`0x0A` | file-transfer TLVs | file service |
| `0x27/0x01` | version/capability TLVs | device version/capability |
| `0x34/0x01` | app IDs | P2P service registry |
| `0x37/0x03` | sport config/dictionary | data dictionary |

The `0x2C/0x01` response for `sequence_data` and `rrisqi_data.bin` was
`0x00023281` ("no new file") during this short session.

## 5. The interval result

Toggling the two settings produced exactly:

```
automatic HR off:   0x07/0x17 -> 01 01 00
automatic HR on:    0x07/0x17 -> 01 01 01
automatic SpO2 off: 0x07/0x24 -> 01 01 00
automatic SpO2 on:  0x07/0x24 -> 01 01 01
```

There is **no interval byte or TLV**. The numeric values nearby are alert
thresholds, not sampling cadence.

**Hard conclusion:** Huawei Health cannot request a faster HR/SpO₂ sampling
interval. Cadence is firmware-controlled. The 1 Hz standard HRS stream is the
fastest verified real-time path on this unit.

## 6. What this enables

- A complete protocol test corpus for a future independent client.
- A known auth family and handshake for HiChain3 work.
- Confirmed settings commands and history request formats.
- A clear boundary between what is possible (on/off, history, 1 Hz HRS) and
  what is not (configurable sampling intervals via the app).

## 7. 24×7 persistence result

- HR Data Broadcast survives screen-off and host disconnect.
- Reaching the band's Settings requires exiting the broadcast; a normal restart
  therefore ends it, and no auto-resume was observed.
- Charging and a forced hard reboot while active were not tested (experiment
  stopped by user choice).
- **Conclusion:** the HRS path provides continuous HR while active but does not
  meet toggle-free 24×7 across restarts. Proprietary authenticated HR is the
  only remaining candidate.

## 8. Decision point: how to get independent auth

The protocol is understood, but the HiChain3 long-term key is account-bound.
There are three practical paths:

### A. Keep the HRS path only (no auth)

- Pros: already working, no reset, no key.
- Cons: 1 Hz HR only; no SpO₂, history, stress, sleep, battery, settings.
- This is the current production-safe state.

### B. Extract the long-term key from Huawei Health (root, no reset)

- Try the app's private storage, HiChain/keystore entries, and runtime
  `HwDeviceAuthManager` / `HiChainAuthManager` state.
- Pros: preserves the band's data and current phone pairing.
- Cons: may be protected by Huawei Keystore/HiChain; no guarantee; keys are
  highly sensitive and must never leave the local machine.

### C. Factory reset + bind a new key (Gadgetbridge or our client)

- Factory reset erases on-device history and unpairs the phone.
- Pair with Gadgetbridge (open source) or a minimal implementation using a
  fresh random key, then export/import that key to the Linux client.
- Pros: clean, reproducible, no Huawei account.
- Cons: data loss; requires explicit consent; firmware may still gate auth.

**Recommendation:** first try **B** (read-only, no reset). If the key is not
accessible, use **C** only with explicit consent. Continue using HRS in the
meantime.

## 9. Firmware note

The unit reports **`Kimi-B19FB`**, firmware **`4.2.0.230(C00M07)`**. This is
newer than the `3.1.0.31` discussed in Gadgetbridge issue #3784 and uses
HiChain3. Do not apply older-firmware assumptions to this unit.

## 10. Reproduction

```bash
# Pull HCI (Android caches btsnoop under cached_hci)
scripts/pull_hci_log.sh captures/android/session.btsnoop
python scripts/parse_btsnoop.py captures/android/session.btsnoop

# Frida logs (local)
scripts/frida_run.sh                 # GATT writes/notifications
frida -U -p <pid> -l scripts/frida_crypto_hooks.js

# Match ciphertext to plaintext
python scripts/analyze_frida_capture.py \
  --gatt captures/android/frida_gatt.log \
  --crypto captures/android/frida_crypto.log \
  --out /tmp/opencode/android/timeline.txt
```
