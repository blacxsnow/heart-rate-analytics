# 14 — Firmware Overhaul Feasibility (Deep Inspection)

**Device:** Huawei Band 9, `Kimi-B19FB`, firmware `4.2.0.230(C00M07)`
**Status:** inspection/feasibility only. **No firmware was read, modified or
flashed.** No case was opened.

---

## 1. Executive conclusion

A full firmware/UI overhaul is **not a realistic first-line option** on this
unit. The evidence points to a signed, secure-boot wearable with no public
recovery path:

- SoC is an **Ambiq Apollo3 Blue Plus (AMA3B)**, Cortex-M4F, which provides
  **Secure Boot**, **Secure OTA**, secure key storage and external-flash
  in-line encryption.
- The band is **glued/sealed**; the teardown shows no exposed debug header.
  SWD may exist on test pads but is not documented.
- Huawei's OTA path is cloud-checked, hash-verified and device-verified. No
  public Band 9 firmware package, signing key or recovery image was found.
- Even a UI-only rewrite would have to be signed by Huawei's key and pass the
  boot chain.

**Recommendation:** keep the independent **software** client as the product.
Only proceed to physical inspection if you accept a meaningful risk of
destroying the band, and only after a recovery plan exists.

---

## 2. Hardware (from teardown, not from our device yet)

Sources:

- EDN China teardown, 2024-09-19:
  <https://www.ednchina.com/technews/30057.html>
- Boardor teardown:
  <https://boardor.com/blog/disassembling-the-huawei-band-exploring-the-main-control-chip>
- Smart Ring Guide summary:
  <https://smartringguide.com/guides/uncover-huawei-band-9-secrets/>

| Component | Part | Notes |
|---|---|---|
| MCU | **Ambiq Apollo3 Blue Plus AMA3B** | Cortex-M4F, FPU, TurboSPOT; secure boot/OTA family |
| PPG | **Goodix GH3020** | multi-channel PPG; HR, HRV, SpO₂ |
| NFC | NXP (marking `110TB2G`) | transit/access cards |
| Motion | ST sensor (marking partly obscured) | 9-axis class |
| Memory | 1 Gbit NAND (marking erased on some units) | likely UI resources / data / external flash |
| Display | 1.47" AMOLED, 368×194 | touch driver separate |
| PMIC/charger | CW6305B, SGM38045 etc. | wearable power tree |
| Battery | HB331531ENW, 180 mAh / 0.70 Wh | ATL cell |
| Case | glued rear cover + glue on PCB | opening is destructive |

The teardown confirms a compact, glue-sealed design with spring contacts and
no service connector. Repairability is poor.

## 3. Boot and security model

The Apollo3 Blue Plus datasheet documents:

- **Secure Boot** and **Standard Boot**
- **Secure OTA**
- **Secure Key Storage**
- **External Flash In-line Encrypt/Decrypt**
- **Serial Wire Debug (SWD)**

Ambiq's EVB documentation explains that factory parts contain a Secure
Bootloader (SBL) and an uninitialized **INFO0** customer information space.
Provisioning INFO0 sets:

- the SBL interface,
- the override pin,
- flash/debug protection,
- the customer keys used to authenticate/decrypt images.

A production Huawei device is expected to have INFO0 provisioned with Huawei
keys and protections enabled. That means:

1. **SWD may be physically present but disabled** by INFO0.
2. Even with SWD, **unsigned firmware will not boot**.
3. A full flash dump may be possible only if debug protection is off; that is
   unknown until inspected.
4. Patching a signed image breaks the signature unless the boot chain has a
   vulnerability or the key leaks.

**Confidence:** hardware family CONFIRMED (teardown); Huawei INFO0/protection
state HYPOTHESIS until read.

## 4. OTA path (from Huawei Health 11.0.0.517)

### 4.1 Version check

`UpdateBase` uses:

```
https://query.hicloud.com/accessory/v2/checkEx.action
```

It sends the device type/version/ID plus phone/account context and receives
version metadata. The response is not a public download; it is an authenticated
Huawei cloud service.

### 4.2 Package verification

`HwVersionManager.isUpgradeFileValid()` verifies the downloaded file with
**SHA-256** and/or **MD5** against server metadata. The device then validates
the image through its secure boot/OTA chain.

### 4.3 Transfer

`DataOtaParametersV2` exposes:

- `otaUnitSize`
- `otaInterval`
- `ackEnable`
- `offsetEnable`
- `appWaitTimeout`
- `deviceRestartTimeout`

The file transfer uses the Huawei file service (`0x0F/*` in our capture), with
offset/ack/unit controls. This matches the general Huawei OTA shape, not a
simple "write this file" command.

### 4.4 What we can inspect without flashing

- The version-check request/response (phone-side capture).
- The downloaded package, if an update is offered (preserve, do not install).
- Package container, compression, signature blocks and image layout.
- OTA transfer TLVs in a controlled check-only flow.

**What we cannot do without keys:** produce a bootable custom image.

## 5. Debug interfaces

| Interface | Status |
|---|---|
| SWD | Apollo3 supports it; not exposed by the sealed design; test pads unknown |
| UART / SBL | Apollo3 SBL can use UART; Huawei provisioning unknown |
| NAND | External NAND likely; direct read requires desoldering/chip-off |
| USB | Charging only (no data) |
| BLE | Application channel, not a bootloader debug channel |

Opening the rear cover requires heat and prying; the teardown shows adhesive
and a fragile assembly. This is a one-way risk unless you have a spare unit.

## 6. Recovery requirements (none currently met)

Before any firmware write, all of these would be required:

1. Full flash dump, verified by two reads and a hash.
2. A known-good recovery image.
3. SWD or UART access to the bootloader.
4. A way to force ROM/SBL mode.
5. Documented INFO0/protection state.
6. A spare device or accepted brick risk.

None are satisfied. Do not flash.

## 7. Staged inspection plan

### Stage 1 — non-destructive (recommended)

1. Reconnect the phone via ADB.
2. Capture a Huawei Health firmware **check** (no install).
3. If a package is offered, download and preserve it; hash it.
4. Analyze container/signature/images statically.
5. Compare with the Ambiq SBL/SSBL image format.
6. Record the exact OTA TLVs and version metadata.

**Stop point:** no writes to the band.

### Stage 2 — destructive, reversible only with a plan

1. Open the rear cover (heat/pry), photograph the PCB and test pads.
2. Identify SWDIO/SWCLK/GND/VCC and any UART pads.
3. Attempt a **read-only** SWD connect with a J-Link/OpenOCD.
4. Read INFO0 and the flash ID **only**; do not erase/write.
5. If debug is locked, stop. Do not attempt glitching.

**Stop point:** any write, erase, or protection change.

### Stage 3 — only if Stage 2 proves an unlocked/recoverable target

Only then consider a custom image. This is a multi-month project: BLE stack,
display, PMIC, sensors, secure boot, OTA, and recovery.

## 8. Decision gate

Firmware work should proceed only if **all** are true:

- SWD is accessible and not protected, or a verified exploit exists.
- A full dump and recovery path are proven.
- The user accepts brick risk and has a spare device.
- The required change cannot be achieved at the software layer.

None are currently true. The software layer already provides measurement-only
operation and 1 Hz HR; the missing pieces (SpO₂/history/persistent mode) are
gated by HiChain3, not by the UI firmware.

## 9. What would change the conclusion

- A public/leaked Huawei signing key (unlikely, and legally sensitive).
- An unlocked INFO0 with SWD enabled on this unit.
- A bootloader/ROM vulnerability with a reliable recovery method.
- A community firmware project for `Kimi-B19` with signed-image bypass.

Without one of these, a firmware overhaul is not an engineering path; it is a
hardware-destruction experiment.
