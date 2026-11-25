# 07 — Rooted Android Reference Environment

The phone is a **temporary measurement instrument**. Nothing in the final
architecture may depend on it.

## 1. Environment (prepared)

| Item | Value |
|---|---|
| Phone | OnePlus 11R 5G (`CPH2487`) |
| Android | 16 |
| Root | Magisk; `su` works from `adb shell` |
| Huawei Health | 11.0.0.517 (installed 2026-11-25) |
| APK | pulled, 99,304,221 bytes |
| JADX | 1.5.7, decompiled to `/tmp/opencode/android/jadx-health` |
| Frida server | 17.27.5 arm64, running as root |
| HCI snoop | active; `/data/misc/bluetooth/cached_hci/btsnoop_hci_*.cfa` |
| ADB | `64609045` |

The APK is decompiled but the code is heavily obfuscated (`o.*`). Static
anchors found so far:

- `o/djr.java` — GATT client: `FE86`, `FE01`, `FE02`; fallback `0x0200/0x0203/0x0202`; notification setup; write queue; reconnect.
- `com/huawei/hwbtsdk/hichain/HiChainAuthManager.java` — HiChain bind/auth,
  session-key callback, PIN.
- `o/dkc.java` — HiChain command TLV builder/parser.
- `o/djp.java` — command queue, V1/V2 conversion, encryption, slicing.
- `o/dig.java` — handshake packet builder and encryption wrapper.
- `o/dip.java` — AES/HMAC helpers.
- `o/dsw.java` — the FitnessData command builder set (`0x07/*`), including
  automatic HR (`0x17`), continuous HR (`0x1C`) and automatic SpO₂ (`0x24`).
- `com/huawei/hwservicesmgr/remote/HwHeartRateManager.java` — live HR
  (`0x19/0x01`) and live-HR data (`0x19/0x03`).
- `com/huawei/hwservicesmgr/remote/utils/RriHeartRateSendCommandUtil.java` —
  stress calibration (`0x20/0x09`, `0x20/0x0A`).
- `defpackage/cej.java`, `defpackage/ddy.java` (older tree) — FE86 UUID constants.
- `assets/product_map.json` — `KIM-B19` = HUAWEI Band 9.

Static command evidence is summarised in `04_protocol_spec.md` §6.2. The key
negative result: the continuous-HR and SpO₂ commands have **no interval
parameter**; they are one-byte on/off toggles.

## 1.1 Runtime capture result (2026-11-25)

The reference environment produced a complete, decrypted session:

- LinkParams: **authVersion 1, deviceSupportType 4 = HiChain3**.
- Security negotiation: auth mode 4, Android ID, phone model.
- HiChain3 JSON exchange captured (`isoSalt`, `token`, `peerAuthId`,
  `returnCodeMac`, success `0x000186A0`).
- FE86 TLV encryption: **AES-GCM**, `0x7C` flag + `0x7D` 16-byte IV +
  `0x7E` ciphertext+tag.
- Command plaintext recovered by matching each ciphertext to the app's
  `Cipher.doFinal` event.
- Confirmed commands include automatic HR (`0x07/0x17`), automatic SpO₂
  (`0x07/0x24`), HR/SpO₂ alerts (`0x1D`, `0x22`, `0x25`), fitness history
  (`0x03`, `0x0A`/`0x0B`, `0x0C`/`0x0D`), sleep/RRI file requests (`0x2C/0x01`),
  file transfer (`0x0F/*`), device version/capability (`0x27/*`), P2P registry
  (`0x34/0x01`) and dictionary sync (`0x37/*`).

The remaining independent-implementation gap is HiChain3 itself: the long-term
key is account-bound, and a factory reset is the clean way to bind a new one.
That decision requires explicit user consent because it erases on-device data.


## 2. Capture policy

- One experiment = one action in Huawei Health.
- Record wall-clock start/end and the phone clock.
- Record the HCI log file name and byte offsets before/after.
- Repeat each experiment twice.
- Keep raw logs local; publish only redacted extracts.
- Never capture or publish account credentials, auth keys or serial numbers.

## 3. Experiment matrix

| ID | Operation | What to capture | Status |
|---|---|---|---|
| E01 | Pair Band 9 with Huawei Health | scan, connect, service discovery, bonding, auth, init | pending |
| E02 | Cold app start with band connected | init command sequence, product/firmware/battery | pending |
| E03 | Open HR screen / measure HR | HR command(s), notifications, rate | pending |
| E04 | Enable HR Data Broadcast | whether app sends a command or only band UI; HRS appearance | pending |
| E05 | Manual SpO₂ measurement | command, duration, notification, result | pending |
| E06 | Toggle automatic SpO₂ | exact TLV, any interval parameter | pending |
| E07 | Stress/HRV measurement | `0x19` commands, RRI/SQI notifications | pending |
| E08 | Sleep/history sync | file/service IDs, chunking, timestamps | pending |
| E09 | Disconnect/reconnect | reconnect auth, stored key, retries | pending |
| E10 | Force-stop/restart app | whether band keeps measuring, resume sequence | pending |
| E11 | Continuous HR: Smart vs Real-time | hidden interval/config TLV | pending |
| E12 | Start a workout | HR notification rate, broadcast interaction | pending |
| E13 | Change band settings (notifications, raise-to-wake) | config commands and battery impact | pending |

## 4. HCI capture procedure

```bash
# Identify the active btsnoop file (the *.log files are text logs, not btsnoop)
adb shell su -c 'ls -lt /data/misc/bluetooth/cached_hci/btsnoop_hci_*.cfa | head'

# Pull while the band is idle (read-only)
adb exec-out su -c 'cat /data/misc/bluetooth/cached_hci/<file>.cfa' > captures/android/e01.btsnoop

# Verify it is btsnoop
file captures/android/e01.btsnoop
```

The Android log is btsnoop format. Decode with Wireshark/tshark if available, or
with the project's parser (planned). The HCI ACL payloads are captured at the
host/controller boundary, so ATT payloads should be visible in plaintext even
when the link is encrypted at the controller.

Correlation rules:

- The band's normal address and broadcast address are different; label both.
- `FE01` writes are host→band; `FE02` notifications are band→host.
- Ignore HID traffic unless it is part of a test.
- Label packets by experiment timestamp, not by guesswork.

## 5. Frida instrumentation

Two levels are useful:

### 5.1 Android framework level (robust, obfuscation-independent)

Hook:

- `android.bluetooth.BluetoothGatt.writeCharacteristic(BluetoothGattCharacteristic)`
- `writeDescriptor(BluetoothGattDescriptor)`
- `readCharacteristic(...)`
- `setCharacteristicNotification(...)`
- `BluetoothGattCallback.onCharacteristicChanged(...)`
- `onServicesDiscovered(...)`
- `onConnectionStateChange(...)`

Log UUID, properties, and hex payloads. This gives the exact GATT timeline even
if Huawei's Java is obfuscated.

### 5.2 Huawei Health level (semantic)

Enumerate loaded classes and hook by name/signature:

- `o.djr` — `b(BluetoothGattCharacteristic)`, write queue, notification handler.
- `o.djp` — `e(byte[])`, `c(dji, byte[])`, `a(dji, byte[])`.
- `o.dig` — `e(Context, byte[], String, DeviceInfo)`, `c(int, DeviceInfo)`.
- `o.dip` — AES/HMAC helpers.
- `o.dkc` — TLV build/parse.
- `com.huawei.hwbtsdk.hichain.HiChainAuthManager` — `c(byte[])`,
  `onSessionKeyReturned`, `onDataTransmit`, `bindPeer`, `authenticatePeer`.
- `com.huawei.security.deviceauth.HwDeviceAuthManager` — bind/auth calls.

Capture arguments and return values as hex. Do not modify return values during
discovery; observe first.

## 6. Static-analysis targets

1. `o/djr.java`: exact service/characteristic flow, MTU request, notification
   descriptor, retry/reconnect.
2. `o/djp.java`: frame serialization, V1/V2 conversion, encryption boundary,
   slicing, command timeout.
3. `o/dig.java`: handshake packet (`dig.c`), encrypted TLV wrapper.
4. `o/dip.java`: AES-CBC/GCM and HMAC details.
5. `o/dkc.java`: HiChain Lite TLVs and result codes.
6. `HiChainAuthManager.java`: bind vs authenticate, session key, PIN.
7. Native libs: `libwhiteBoxJniLib.so` (mentioned by earlier research),
   `libJniRRI.so`, `libModule_AM16_RRI.so`, `libDetailStressJni.so` — only if
   Java-level capture is insufficient. Do not reverse native crypto first.

## 7. Application storage

After pairing, inspect (root):

```
/data/data/com.huawei.health/databases/
/data/data/com.huawei.health/shared_prefs/
/data/data/com.huawei.health/files/
```

Look for:

- device identity (`KIM-B19`, MAC, serial)
- firmware/software version
- auth/bind state and keys (never publish)
- measurement tables and timestamp/unit conventions
- sync cursors

Huawei Health commonly uses SQLCipher for health databases. If a DB is
encrypted, do not spend time cracking it before the HCI capture; the BLE
protocol is the primary source. The app's own display is the ground truth for
comparison.

## 8. Controlled comparison

For each metric, compare:

1. Band display.
2. Huawei Health display.
3. Independent client value.

Record timestamp, value, unit, and the offset between sources. A metric is only
"verified" when all three agree within a stated tolerance.

## 9. Deliverables from this phase

- `captures/android/*.btsnoop` (local, gitignored).
- A decoded command timeline per experiment.
- A Frida hook script and its logs.
- Updates to `04_protocol_spec.md` with confidence tags.
- A short "Huawei Health communication architecture" report.

## 10. Exit criteria

The Android phase ends when:

- auth is understood well enough to implement independently, and
- the HR/SpO₂/history commands are identified, and
- a Linux client can reproduce at least one proprietary operation without the
  phone.

Then the phone is removed from the runtime architecture.
