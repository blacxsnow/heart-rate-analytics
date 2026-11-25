# 02 — BLE Reconnaissance Report

**Device:** Huawei Band 9, model `KIM-B19`
**Host:** Fedora Linux, BlueZ 5.88, Bleak 3.1.0
**Date:** 2026-11-25
**Method:** passive/active BLE scan + read-only GATT enumeration. No pairing, no
bonding, no vendor writes.

Addresses are redacted as `<NORMAL_ADDR>` and `<BROADCAST_ADDR>`.

---

## 1. Two advertising endpoints

A single physical band presents two different BLE identities depending on mode.

| Property | Normal endpoint | HR Data Broadcast endpoint |
|---|---|---|
| Advertising name | `HUAWEI Band 9-<suffix>` | `HUAWEI Band HR-<suffix>` |
| Address | `<NORMAL_ADDR>` (`<redacted>`) | `<BROADCAST_ADDR>` (`<redacted>`) |
| Advertised service | `0x3802` | `0x180D` (+ cached vendor services in active scan) |
| Manufacturer data | key `0x027D`, `01 03 00 ff ff` | same |
| TX power | — | `+4 dBm` |
| Connectable | yes | yes |
| Standard HR service | no | **yes** |

The two addresses share the name suffix and the last bytes, but the first octet
differs (`54` vs `D4`). This is consistent with a derived/randomised identity
for broadcast mode. **Always discover by name or service UUID.**

When HR Data Broadcast is active, the normal `HUAWEI Band 9-…` name is no longer
advertised (observed repeatedly). When broadcast is exited, the normal endpoint
returns.

## 2. Verified advertisement records

Normal mode:

```text
<ADDR>  RSSI -64  "HUAWEI Band 9-<suffix>"
  service_uuids: 00003802-0000-1000-8000-00805f9b34fb
  manufacturer:  0x027D = 01 03 00 ff ff
  service_data:  00003802 = <6-byte address>
  flags:         0x04
  connectable:   yes
```

HR broadcast mode:

```text
<ADDR>  RSSI -66  "HUAWEI Band HR-<suffix>"
  service_uuids: 0000180d-0000-1000-8000-00805f9b34fb
  manufacturer:  0x027D = 01 03 00 ff ff
  tx_power:      +4
```

The vendor service `0x3802` is also present in the broadcast endpoint's GATT
table even though it is not the first advertised UUID.

## 3. GATT map — normal endpoint

Read-only enumeration succeeded while the band accepted a connection.

| Service | Characteristic | Properties | Notes |
|---|---|---|---|
| `FE86` Huawei Link | `FE01` | write, write-no-response | host → band |
| | `FE02` | notify (CCCD) | band → host |
| `1800` GAP | `2A00` | read | Device Name |
| | `2A01` | read | Appearance |
| | `2AA6` | read | Central Address Resolution |
| `1801` GATT | `2B29` | read | Database Hash |
| | `2B2A` | read | Server Supported Features |
| | `2A05` | indicate | Service Changed |
| `180A` Device Info | `2A24`–`2A29` | read | Model, serial, firmware, hardware, software, manufacturer |
| `3802` vendor | `4A02` | read, write, notify | role unknown |
| `E2E3` vendor | `E2E5` | read, notify | role unknown |
| | `E2E4` | write, write-no-response | role unknown |
| `CC353442-BE58-4EA2-876E-11D8D6976366` | `C551C36A-0377-4A29-9657-74FFB655A188` | read, write, notify | role unknown |
| `1812` HID | `2A4A`–`2A4E`, `2A22`, `2A32` | read/write/notify | HID over GATT |
| `E2CB` vendor | `E914` | write, write-no-response | role unknown |
| | `1A19` | read, notify | role unknown |

### Service count

9 primary services, 30+ characteristics. The proprietary role of the vendor
services (`3802`, `E2CB`, `E2E3`, `CC353442`) is **unknown** and not required
for HRS. They are recorded for completeness and future investigation.

## 4. GATT map — HR broadcast endpoint

The same services as above **plus** the standard Heart Rate service:

| Service | Characteristic | Properties | Notes |
|---|---|---|---|
| `180D` Heart Rate | `2A37` | notify | **verified live** |
| | `2A38` | read | Body Sensor Location = `0x02` (wrist) |
| | `2A39` | write | Heart Rate Control Point |

`0x2A38` returns `02` = wrist. `0x2A39` was not written (standard control point
only resets energy expended; not needed).

## 5. Verified heart-rate stream

Connection: no pairing, no auth, no Huawei account.

First run (30 s):

```text
1795600771.6416 +01.12s 065f  flags=0x06 hr=95
1795600772.6317 +02.11s 0660  flags=0x06 hr=96
...
1795600800.6658 +30.15s 065d  flags=0x06 hr=93
packets=30
```

Second run (screen-off soak):

```text
packets:     213
span:        212.4 s
mean period: 1.002 s
max gap:     1.17 s
gaps > 2 s:  0
```

Decoded flags:

- bit 0 = 0 → 8-bit heart rate
- bit 1 = 1 → sensor contact supported
- bit 2 = 1 → sensor contact detected
- bit 3 = 0 → no energy expended
- bit 4 = 0 → **no RR intervals**

**Consequences:**

- HR is available at ~1 Hz.
- HRV cannot be derived from this endpoint because no RR/beat-to-beat data is
  present.
- Values in the 90s were plausible for the wearer at rest (not a synthetic
  constant).

## 6. Device Information Service caveat

On the broadcast endpoint the DIS values are generic placeholders:

| Field | Value |
|---|---|
| Manufacturer | `HUAWEI` |
| Model Number | `HUAWEI` |
| Serial Number | `HUAWEI` |
| Firmware Revision | `1.0.0.1` |
| Hardware Revision | `1.0.0.1` |
| Software Revision | `1.0.0.1` |

On the normal endpoint, a DIS read returned GATT `Unlikely Error` (`0x0E`).
Therefore **DIS is not a reliable source of the real firmware version**. Real
product/firmware identifiers are obtained through the proprietary product-info
command after authentication (Gadgetbridge `GetProductInformationRequest`).

## 7. Proprietary-channel observations

The `FE86` service is present on both endpoints. On the HR-broadcast endpoint it
did **not** answer the documented LinkParams handshake (no `FE02` notification
within 12 s). On the normal endpoint, BlueZ connected and resolved services, but
a second Bleak connection attempt caused a disconnect during service discovery;
this is a host/link-contention issue, not necessarily a protocol rejection.

The next step is to capture the normal endpoint through the rooted Android
reference phone and replay the exact handshake. See
`07_android_reference_plan.md`.

## 8. Reproduction

```bash
band9 endpoints
band9 gatt --endpoint hr_broadcast --subscribe 20
band9 hr --duration 60
```

Raw JSONL captures and the SQLite database are kept local and gitignored.
Sanitised GATT JSON is stored in `captures/gatt/`.

## 9. Confidence

| Finding | Confidence |
|---|---|
| Two distinct advertising identities | **CONFIRMED** (repeated scans) |
| Standard 0x180D in broadcast mode only | **CONFIRMED** |
| 1 Hz HR, uint8, contact bit | **CONFIRMED** (213 packets) |
| No RR intervals in HRS | **CONFIRMED** |
| Broadcast survives screen-off | **CONFIRMED (3.5 min)** |
| Broadcast survives disconnect/reconnect | **CONFIRMED** (host reconnect) |
| Broadcast survives reboot/charging | **UNTESTED** |
| DIS values are placeholders | **CONFIRMED** |
| Vendor service roles | **UNKNOWN** |
