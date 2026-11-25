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
- Huawei's OTA path is cloud-checked, hash-verified and device-verified. A
  signed Band 9 update container was obtained and inspected (Stage 1); it
  carries a 384-byte authentication block, per-component SHA-256 digests and
  a dedicated Ambiq secure-boot image.
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

### 4.1 Version check (captured 2026-11-25)

The live Huawei Health 11.0.0.517 code path is obfuscated (`mkl` / `mkp` /
`kka`), not the `UpdateBase`/`eja` classes described by older decompiles. The
captured check is an HTTPS POST of JSON to:

```
https://update-dre.platform.hicloud.com/ring2/v2/CheckEx.action?ruleAttr=true
https://update-dre.platform.hicloud.com/Ring/v2/CheckEx.action?ruleAttr=true  (fallback)
```

Request shape (values redacted here):

```json
{
  "components": [{
    "PackageName": "com.huawei.KIM-B19.firmware",
    "PackageVersionCode": "0",
    "PackageVersionName": "<current firmware>",
    "SearchType": "1"
  }],
  "rules": {
    "DeviceName": "KIM-B19",
    "FirmWare": "ro.build.display.id",
    "deviceId": "<band serial>",
    "extra_info": "{\"phdDeviceUdid\":\"<device UDID>\",\"appVersion\":\"<code>\"}",
    "Language": "...", "OS": "Android ...",
    "C_version": "ro.product.CustCVersion",
    "D_version": "ro.product.CustDVersion",
    "vendorcountry": "..."
  }
}
```

Response either says `{"status":"1"}` ("Your version is up to date") or
`{"status":"0","components":[{name,version,versionID,createTime,url,size}]}`.
The package directory is then fetched as `<url>full/filelist.xml`.

### 4.2 Package verification

`filelist.xml` lists each file with **size, MD5 and SHA-256**. The app checks
the downloaded file against those values, and the band validates the container
and images through its OTA/secure-boot chain. The container itself also carries
per-component SHA-256 digests (section 4.5).

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

### 4.5 Stage 1 result: package obtained and parsed (2026-11-25)

No update is offered for the installed `4.2.0.230(C00M07)`; the UI reports
"Your version is up to date" and the server answers `{"status":"1"}`.

In our tests only the **immediate previous release** produced an offer. By
replaying the same check with the claimed version set to `4.2.0.226(C00M06)`,
the server returned:

```
status     0
version    4.2.0.230(C00M07)
versionID  924903
createTime 2026-09-13T16:00:00+0000
url        https://update.hicloud.com/download/data/pub_13/HWHOTA_hota_900_9/.../
```

That directory contains `changelog.xml` (206,248 bytes; SHA-256
`a7ff5649…b06a2d`, matching `filelist.xml`) and:

```
Kimi_DIFF_4.2.0.226(C00M06)-4.2.0.230(C00M07).bin.apk
size      8,600,225 bytes
sha256    e027ff7af65b7a647675edc235504d72d5288f34c8668ed47ffe8e47b1da42f1
```

The changelog names the internal platform baseline
`U9200-1V100R001CHNC00B018` (component `TCPU`), which differs from the
marketing firmware string.

The file was downloaded and its SHA-256 matched `filelist.xml`. It was **not**
sent to the band. Claimed versions older than `4.2.0.226` returned
`status 1`, so no arbitrary full image is exposed by the service.

Despite the `DIFF` name, the container stores **complete component images**
(each SHA-256 matches its payload slice); it is consistent with a file-level
delta, not a binary patch set. Format (version 1):

| Offset | Field |
|---|---|
| `0x00` | u16 layout version (`1`) |
| `0x02` | u16 header length (`0x88`) |
| `0x04` | u32 signature offset (`0x11c1`) |
| `0x08` | u32 unknown (`1`) |
| `0x0c` | char[64] product tag (`Kimi`) |
| `0x4c` | char[64] package version (`4.2.0.230(C00M07)`) |
| `0x8c` | u16 tag 2, u16 length `0x20`, build date/time (`2026.08.28 12:06:45`) |
| `0xb0` | u16 tag 5, u16 manifest length (`0x1090`) |
| `0xb4` | 20 manifest entries, `0xd4` bytes each |
| `0x11c1` | 384-byte high-entropy authentication block |
| `0x1341` | payload: concatenated component images |

Each manifest entry is `name[64]`, `reserved[60]`, `flags[6]`, `version[10]`,
`u32 size`, `u32 crc32`, `sha256[32]`, `source_digest[32]`. The second digest is
**not** the payload MD5; it is believed to identify the previous file version.

Components in this delta:

| Component | Size | Notes |
|---|---:|---|
| `kimi_am35_recovery.bin` | 178,352 | recovery image |
| `kimi_am35_secboot.bin` | 4,736 | Ambiq secure-boot stage |
| `kimi_am35_application.bin` | 1,816,698 | main application |
| `xip_code.bin` | 4,268,038 | execute-in-place code |
| `reserv7.bin` | 1,141,830 | reserved region |
| `glyphs.bin` | 229,821 | UI glyphs (v27.0.122) |
| `logo.bin`, `gui09.bin`, `gui10.bin`, watchfaces 3–5 | 15,716 / 72 ×5 | UI assets |
| `nfc_sn110t_fw_v60.bin` | 204,518 | NFC firmware |
| `tp_fw_kimi.bin` | 125,772 | touch-panel firmware |
| `i18n.dat`, `open_source.zip`, `wechatpay_auth.bin` | 76,654 / 401,957 / 416 | data |
| `cak.bin`, `source_crc.bin` | 40 / 68 | key/CRC metadata |

All 20 components verified against their SHA-256. The application image starts
with an Ambiq Apollo3 vector table (`SP = 0x100bf0f0`,
`reset = 0x001de069`), confirming a Cortex-M image, and a separate secure-boot
image is shipped. The 384-byte block at `0x11c1` is the size of an RSA-3072
signature; its scheme and key were not resolved, but its presence plus the
per-file digests is consistent with signed-container verification.

Tooling (no device access, no secrets):

- `scripts/frida_ota_hooks.js` — read-only observer for the live check.
- `src/fitness_band/hota.py` — container parser/verifier.
- `scripts/inspect_hota.py` — CLI (`--extract`, `--json`, SHA-256 checks).

**Stage 1 stop point reached:** package captured, hashed, parsed and archived
locally. No band write, no install, no case opening.

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

### Stage 1 — non-destructive (recommended) — **complete 2026-11-25**

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
