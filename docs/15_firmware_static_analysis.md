# 15 — Firmware Static Analysis (Track A)

**Scope:** offline analysis of the OTA component images obtained on 2026-11-25.
No device was opened, flashed, or modified. No signature bypass was attempted.

**Inputs:** `Kimi_DIFF_4.2.0.226(C00M06)-4.2.0.230(C00M07).bin.apk`
(SHA-256 `e027ff7a…1da42f1`, verified against `filelist.xml`).

---

## 1. Image map

The container stores four executable images plus resources. Load addresses were
derived from the Cortex-M vector tables; `xip_code.bin` was solved from
PC-relative string literals (see §2).

| Image | Size | Load base | Entry / vector evidence | Role |
|---|---:|---:|---|---|
| `kimi_am35_secboot.bin` | 4,736 | `0x0000D000` | SP `0x10001700`, reset `0x0000D1D5` | Secure-boot / first-stage loader |
| `kimi_am35_recovery.bin` | 178,352 | `0x0003A000` | SP `0x1008C960`, reset `0x0003A629` | Recovery: flash, MSPI, LCD, update UI |
| `kimi_am35_application.bin` | 1,816,698 | `0x00100000` | SP `0x100BF0F0`, reset `0x001DE069` | Main firmware: OpenHarmony framework, PPG, storage, UI |
| `xip_code.bin` | 4,268,038 | `0x06040000` | 96/120 sampled string literals equal `base + offset` | XIP code + rodata: BLE stack, HiChain3/HKS, OSA/health, UI resources |
| `glyphs.bin`, `logo.bin`, `gui*.bin`, `watchface*.bin` | — | — | resource data | UI assets |
| `nfc_sn110t_fw_v60.bin`, `tp_fw_kimi.bin` | — | — | vendor images | NFC and touch firmware |
| `source_crc.bin`, `cak.bin` | 68 / 40 | — | opaque metadata | update/source checksums and key metadata |

The address space is consistent with an Ambiq Apollo3-class MCU (Cortex-M4F,
Thumb-2) using MRAM for the boot stages and MSPI/XIP-mapped external flash for
the application and the 4.2 MB XIP image.

`xip_code.bin` begins with a 64 KB table of 16-bit values and has code density
(Thumb prologues/`bx lr`) from `0x10000` to about `0x380000`, followed by rodata
and UI strings from about `0x3C0000`. The table is not an ELF header; it is a
loader/layout table and was not fully decoded.

## 2. How the XIP base was established

The image is stripped and uses literal pools. A candidate base `B` was scored by
checking whether `B + string_file_offset` appears as a 32-bit literal in the
image. For 120 random strings, `B = 0x06040000` matched 96; every other
page-aligned candidate in the plausible flash range matched 0. This is a strong
confirmation, not a guess.

Example references (file offset → virtual address):

| String | File offset | Address |
|---|---:|---:|
| `hichain_iso_exchange` | `0x3DCDE4` | `0x0641CDE4` |
| `hichain_iso_session_key` | `0x3DCDFC` | `0x0641CDFC` |
| `hichain_return_key` | `0x3E1FC8` | `0x06421FC8` |
| `HichainThread` | `0x3ECB78` | `0x0642CB78` |
| `HksServiceEncrypt` | `0x3E1E60` | `0x06421E60` |

## 3. Operating system and application architecture

`kimi_am35_application.bin` identifies the platform as **OpenHarmony**:

- Version strings: `OpenHarmony 2.3 beta`, `OpenHarmony-3.2.10.6`,
  `OpenHarmony 1.0.1` (file offsets `0x1A20AC`, `0x1A20F4`, `0x1A423C`).
- OHOS C++ typeinfo/UI classes: `N4OHOS…` (APPFWK, `UIImageAnimatorView`,
  `UICheckBox`, `UIScrollView`, `UISlider`, `UISwipeView`, notifications).
- Task/service infrastructure: `Service<name:%s…> create taskPool failed!`,
  `message watchdog timeout task<%s…>`, `stack overflow task name %s`,
  `schedule watchdog timeout task`.
- Parameter service: `InitParamService`, `LoadPersistParam`,
  `Failed to save persist param`, `ReadParamWithCheck`.
- File system: VFS/mount strings in application and recovery; NAND drivers
  `ds35x1g`, `fm25ls01`, `w25n01g`; MSPI configuration/power-on.

The kernel is an OpenHarmony-family RTOS (LiteOS lineage); the exact kernel
variant is not proven from strings alone. The application is not a bare-metal
loop: it has tasks, watchdogs, a parameter service, a UI framework, and a
separate BLE/protocol subsystem.

## 4. BLE stack and proprietary transport

The XIP image contains a Bluedroid/GKI-style host stack:

- `gki_alloc_free_queue: Not enough memory`
- `btl2cap://`
- HCI/ACL/L2CAP markers and advertising/pairing strings.

The application GATT transport is the FE86 service (`FE01` write, `FE02`
notify) documented in `04_protocol_spec.md`. The proprietary command layer and
the HiChain3 authentication live above that transport; they are separate from
the standard HRS service.

The XIP image also contains the band-side **HiChain3** implementation:

| Evidence | Meaning |
|---|---|
| `hichain_iso_exchange`, `hichain_iso_session_key`, `hichain_iso_result`, `hichain_return_key` | ISO session-key exchange / return-key handling |
| `HichainThread` | dedicated auth thread |
| `HksServiceInitialize/Encrypt/Decrypt/DeleteKey/KeyExist/ImportKey/DeriveKey` | Huawei KeyStore (HKS) operations |
| `/user/deviceauth/hcgroup.dat`, `%s/hcgroup%d.dat`, `/user/deviceauth` | HiChain group/key files on the device |
| JSON keys `authForm`, `peerAuthId`, `isoSalt`, `returnCodeMac`, `operationCode`, `groupAndModuleVersion`, `peerUserType` | same HiChain3 JSON vocabulary captured from Huawei Health |

This confirms the architectural split: the **phone is the HiChain client**, the
**band is the HiChain peer/server**, and long-term group material is stored in
`/user/deviceauth` under HKS, not in the OTA image.

## 5. Physiological acquisition

The application image contains the optical/wear pipeline:

- `HWD PPG config changed option,period:%u,%u`
- `HWD in HwdIrDataProcess data size is 0.`
- `HWD Health Wear On/Off Event`
- `HWD IrResultCalculate`, `HWD HrLivenessDetect`
- `HWD alg_result changed`, `HWD period result final`

Health algorithms are present in both images: `Sleepass Alg1.2` (sleep),
OSA/SpO2 (`osa_spo2_data.bin`, `osaSpo2FeatData*.bin`), arrhythmia, and
RRI/sleep-RRI model files.

Persistent health data is file-backed (XIP image paths):

| File | Content |
|---|---|
| `/user/data/health/hrm_historydata.bin` | historical HR |
| `/user/data/health/heartrate_data_sleep.bin` | sleep HR |
| `/user/data/health/spo2.bin`, `spo2_data_sleep.bin` | SpO2 |
| `/user/data/health/spo2_curve.bin`, `spo2_remind.bin` | SpO2 curve/alerts |
| `/user/data/health/osa_spo2_data.bin` | OSA/sleep-apnea SpO2 |
| `/user/data/health/arrhythmia_ppg_localdata_new.bin` | arrhythmia PPG data |
| `/user/data/health/sleep_rri_model_feature.bin`, `rir_data_sleep.bin` | RRI |
| `/user/data/health/sample_data.bin`, `sample_state.bin` | sampling state |

## 6. Power and scheduling

The images contain a task scheduler with message/schedule watchdogs, a
parameter/persistence service, RTC strings, battery/power management, and the
`Sleepass` sleep-state algorithm. This is a tick-driven RTOS design, not a
single-threaded UI loop. Precise PMU/wake-source behavior needs runtime
tracing; the static evidence only establishes that power and scheduling are
central services.

## 7. Secure boot and update authentication

- A dedicated secure-boot image (`kimi_am35_secboot.bin`) is shipped and loads
  at `0x0000D000`; the application and recovery are separate images.
- The HOTA container has a 384-byte authentication block between the manifest
  and the payload, plus a SHA-256 digest per component (see
  `14_firmware_feasibility.md`).
- HKS and `/user/deviceauth` hold device auth material outside the OTA images.
- No signing keys, private keys, or group keys were found in the package.

**Conclusion:** the OTA/secure-boot chain is real and signed. There is no
evidence of a signature bypass, and none was attempted.

## 8. Is acquisition independent of the smartwatch UI?

**Architecturally, yes for the acquisition/storage pipeline; no for policy.**

- PPG sampling, wear detection, HR/SpO2 algorithms, and file persistence are
  separate services/tasks with their own storage paths. They do not depend on
  the UI rendering loop.
- The UI is a distinct OpenHarmony subsystem (UI toolkit classes, watchfaces,
  GUI assets).
- However, automatic HR/SpO₂ are gated by settings commands (`0x07/0x17`,
  `0x07/0x24`) and firmware policy. Removing or simplifying the UI would not by
  itself enable 24×7 acquisition; the control layer still decides when the
  sensor runs.

This supports a **headless acquisition mode** as a firmware design direction,
but not as a simple “disable the UI” switch.

## 9. Modification feasibility

Unchanged from the Stage 1 conclusion: a custom image requires Huawei’s signing
key and a recovery path. The images provide architecture knowledge, not a
bypass. Do not flash.

## 10. Open questions

1. Exact OpenHarmony kernel variant and task priorities.
2. Semantics of the 64 KB XIP layout table.
3. Command dispatch tables for `0x07`, `0x19`, `0x2C` and their handlers.
4. Whether the band accepts a new HiChain3 bind from an independent peer.
5. Which health files are exposed through the file service and under what
   authentication.
