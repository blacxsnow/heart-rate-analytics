# 08 — Firmware Investigation (Desk Review and Guardrails)

**Status: not started physically. No firmware was read, modified or flashed.**

This document exists to prevent premature firmware work. The software path
already delivers the minimum outcome, and most of the user's goals
(SpO₂, history, intervals) are more likely to be solved at the protocol layer.

---

## 1. Why firmware is not the first move

- Standard HRS works with no firmware changes.
- The proprietary channel is documented by Gadgetbridge/Huawhoop and is the
  likely route to SpO₂/history/intervals.
- Firmware modification has a high brick risk and no known Band 9 recovery path.
- The Band 9 is a closed, signed wearable; the bootloader/SoC are not publicly
  documented for this model.

## 2. What is known

| Item | Status |
|---|---|
| Model | `KIM-B19` (confirmed) |
| OS | Huawei LiteOS / HarmonyOS Lite family (family-level, not confirmed for this unit) |
| SoC | unknown |
| Flash | unknown |
| Bootloader | unknown |
| Debug pads | not mapped |
| Firmware format | unknown |
| Signing/verification | almost certainly present; unverified |
| OTA delivery | via Huawei Health (observed candidate path) |
| Public Band 9 firmware RE | none found in the surveyed projects |
| Recovery image | none known |

Do not fill these gaps with guesses.

## 3. Firmware acquisition (read-only)

If needed later:

1. Capture the OTA download performed by Huawei Health on the rooted phone
   (proxy, file system, or app-private storage).
2. Record the exact version string and package hash.
3. Preserve the original package; do not modify it.
4. Identify container/compression/encryption and signature blocks.
5. Check whether the package is device-specific and anti-rollback protected.

This is analysis only; no write to the band.

## 4. Hardware interfaces

Only pursue if the software path is exhausted:

- Inspect the rear case/strap attachment for pogo pins or test pads.
- Look for UART/SWD labels; do not probe blindly with power applied.
- Use a current-limited supply and a logic analyser.
- Identify the SoC before attempting any debug access.
- Establish a dump/restore path before any write.

No destructive probing is authorised by this document.

## 5. Recovery requirements

Before any firmware write (not planned):

- Full flash dump, verified by two reads and a hash.
- Known-good recovery image.
- UART/SWD access to the bootloader.
- Ability to force DFU/ROM mode.
- A spare device or accepted brick risk.
- Documented rollback procedure.

None of these are currently satisfied.

## 6. The "measurement-only UI" and battery goal

The user wants:

- only measurement features,
- maximum battery life,
- aggressive/configurable sampling.

These pull in opposite directions: higher sampling = more PPG LED/CPU time =
more battery drain. The realistic levers are:

1. **Disable notifications, calls, media, weather, watchface animations,
   raise-to-wake, always-on display** via settings or the companion app.
2. **Use the lowest display brightness/timeout.**
3. **Choose a sampling policy**: 1 Hz HRS is already continuous; higher rates
   will cost battery. Measure the drain before optimising.
4. **Avoid unnecessary BLE connections**: each reconnect and sync costs energy.
5. **Do not rewrite firmware.** A custom UI is a large, signed-firmware project
   with no recovery path.

An independent client can present a measurement-only *software* UI and ignore
all non-measurement features without touching the band's firmware.

## 7. Decision gate

Firmware work starts only if all of the following are true:

- The proprietary protocol cannot provide the required metric or interval.
- The limitation is proven to be firmware-side, not app-side.
- A recovery path exists.
- The user explicitly accepts the brick risk.

Until then, firmware remains out of scope.
