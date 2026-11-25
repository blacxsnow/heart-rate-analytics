# 03 — Device and Firmware Identification

**Date:** 2026-11-25
**Physical device:** Huawei Band 9
**Marketing name:** HUAWEI Band 9
**Model:** `KIM-B19` (confirmed from Huawei Health's `product_map.json`)
**Advertised name suffix:** `<redacted>`

---

## 1. What is confirmed

| Identifier | Value | Source | Confidence |
|---|---|---|---|
| Model family | `KIM-B19` | Huawei Health 11.0.0.517 `assets/product_map.json` | **CONFIRMED** |
| Device type string | `Kimi-B19FB` | proprietary device-info response (`0x27/0x01`), captured 2026-11-25 | **CONFIRMED** |
| Firmware | `4.2.0.230(C00M07)` | same proprietary device-info response | **CONFIRMED** |
| Marketing name | HUAWEI Band 9 | product_map.json (`marketingName`) | **CONFIRMED** |
| Product UUID | `24572deb-6b22-4a10-ab5d-4aa3c20c87d1` | product_map.json | **CONFIRMED** |
| Device type id | 747–750, 761, 811 (regional/variant entries) | product_map.json | **CONFIRMED** |
| Body sensor location | `0x02` = wrist | GATT `0x2A38` | **CONFIRMED** |
| Standard HRS present in broadcast mode | yes | GATT + live stream | **CONFIRMED** |
| Normal endpoint advertising service | `0x3802` | BLE scan | **CONFIRMED** |
| Proprietary transport | `FE86` / `FE01` / `FE02` | GATT + Huawei Health static analysis | **CONFIRMED** |

The `product_map.json` entries include several `KIM-B19` variants
(`M0DF`, `M0DG`, `M0DH`, `M0DI`, `M0DS`, `M0EG`), plus `KIM-B19B` for a
different marketing name (`HUAWEI Band HA590`). The unit reports
`Kimi-B19FB` in the proprietary device-info payload; the exact regional
suffix remains a device-specific detail and is not published here.

## 2. Firmware and DIS caveat

The real firmware is **`4.2.0.230(C00M07)`**, read from the authenticated
proprietary device-info response. This is newer than the `3.1.0.31` firmware
mentioned in Gadgetbridge issue #3784 and is consistent with the observed
**HiChain3** auth family.

The standard Device Information Service still returns placeholders:

```
Manufacturer      HUAWEI
Model Number      HUAWEI
Serial Number     HUAWEI
Firmware Revision 1.0.0.1
Hardware Revision 1.0.0.1
Software Revision 1.0.0.1
```

These are not credible identifiers. The normal endpoint returned GATT
`Unlikely Error` on a DIS read. The real values are exposed by the proprietary
product-information command after authentication (Gadgetbridge
`GetProductInformationRequest`; the captured device-info payload used
`0x27/0x01`).

### Why firmware matters

Gadgetbridge issue #3784 reports that a Band 9 updated to firmware
`3.1.0.31` (after pairing with Huawei Health) failed to authenticate with
Gadgetbridge, while an older firmware worked. The issue contains a workaround
that changes the pairing path; the workaround helped Band 9/Band 7 but broke
Band 8/GT4 in one iteration. This unit is on `4.2.0.230(C00M07)` and uses
HiChain3, so results from the older firmware cannot be assumed to apply.

- Firmware version affects the **auth path**, not the HRS path.
- The firmware is now recorded, so future comparisons are possible.
- Do not assume a Gadgetbridge fix for one firmware applies to another.

## 3. How to obtain the real identifiers

In priority order:

1. **Proprietary product info after authentication** — the authoritative route.
   Gadgetbridge: `GetProductInformationRequest`; expected fields include product
   model, firmware, software, hardware, serial, MAC.
2. **Huawei Health UI** — device details screen usually shows model, firmware,
   serial and MAC. Record a photo/screenshot for the lab notebook.
3. **Huawei Health private storage** — on the rooted phone, device metadata is
   stored in SQLite/shared preferences. Search for `KIM-B19`, `firmware`,
   `deviceIdentify`.
4. **Firmware update package metadata** — Huawei Health downloads an OTA package;
   its filename/manifest may contain the version. Do not flash.
5. **Physical label/box** — model and serial are on the rear case/box.

## 4. Reference environment identifiers

For reproducibility (not the final runtime):

| Item | Value |
|---|---|
| Phone | OnePlus 11R 5G (`CPH2487`) |
| Android | 16 |
| Root | Magisk (`su` available, `u:r:magisk:s0`) |
| Huawei Health | `com.huawei.health` 11.0.0.517 (versionCode 1010050517) |
| APK size | 99,304,221 bytes (base.apk) |
| Frida server | 17.27.5, arm64 |
| HCI snoop log | `/data/misc/bluetooth/cached_hci/btsnoop_hci_*.cfa` |
| HCI logging | active (log grows during scans/connections) |

The APK was pulled from the phone and decompiled with JADX 1.5.7. Static
analysis found the real BLE client in `o/djr.java` (FE86/FE01/FE02) and the
HiChain wrapper in `com/huawei/hwbtsdk/hichain/HiChainAuthManager.java`.

## 5. Privacy handling

- Public documents use `<NORMAL_ADDR>` / `<BROADCAST_ADDR>` instead of MACs.
- Serial numbers and auth keys are never committed.
- Raw HCI logs, APK-derived personal data, and the SQLite database stay in
  gitignored local directories.
- The Android reference environment is temporary; the final client must run on
  Linux without Huawei Health.

## 6. Open questions

1. Exact firmware string and build date.
2. Whether the unit is `KIM-B19` or a regional variant (`KIM-B19B`).
3. Whether the unit was ever bound to a Huawei account (affects auth).
4. Whether the normal endpoint auth key is account-derived or device-generated
   on this firmware.
5. Whether the firmware supports the Band 10-style live HR/RRI commands.
