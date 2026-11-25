# 09 — Physiological Measurement Availability Matrix

Classification:

- **A. Real-time** — streamed while measuring.
- **B. Historical sync** — stored on the band, downloaded later.
- **C. Device-internal** — computed by the wearable firmware (may only be
  exposed as a summary).
- **D. App-derived** — computed by Huawei Health or a third party from raw(ish)
  data.

The Band 9 does **not** expose raw PPG. All optical metrics are processed on
the device.

| Metric | A real-time | B historical | C device-internal | D app-derived | Status on this unit |
|---|---|---|---|---|---|
| Heart rate | **yes, HRS 1 Hz (verified)**; proprietary live HR hypothesis | likely (`0x07` fitness minutes) | yes | possible | **A verified** |
| Resting heart rate | no direct stream | likely | yes | possible | not verified |
| SpO₂ | not in HRS; live proprietary unknown | likely (`0x07` samples, 74/24 h on Band 10) | yes | possible | not verified |
| HRV (RMSSD etc.) | **no** in HRS (no RR); live RRI hypothesis (`0x19/0x05`) | sleep-sequence HRV likely | yes (TruSleep/stress) | yes | not verified |
| RR intervals | no in HRS | maybe in workout/history | — | — | not verified |
| Steps | no | likely (`0x07/0x0A`) | yes | possible | not verified |
| Activity/calories | no | likely | yes | possible | not verified |
| Sleep duration | no | likely | yes | possible | not verified |
| Sleep stages | no | likely (TruSleep) | yes | possible | not verified |
| Stress | no | likely | yes | possible | not verified |
| Skin temperature | no | possibly (`SetSkinTemperatureMeasurement`) | yes | possible | not verified |
| Battery | no | yes (proprietary) | yes | — | not verified |
| Raw PPG | no | no | — | — | almost certainly unavailable |

## 1. Heart rate (the verified path)

- Standard HRS `0x180D/0x2A37`.
- ~1 Hz, uint8 BPM, contact bit, no RR.
- Started manually on the band: **Settings → HR Data Broadcasts**.
- Survives screen-off and host disconnect (verified).
- **No Huawei account required.**

## 2. SpO₂

- Not part of standard HRS.
- Huawei Health exposes SpO₂ as a spot measurement and an automatic mode.
- Gadgetbridge has `EnableAutomaticSpo` (`0x07/0x24`) and an SpO₂ sample
  provider, but this is not yet exercised on the Band 9.
- Huawhoop's Band 10 history contained 74 SpO₂ samples in 24 h (~20-minute
  spacing), suggesting a device-controlled periodic cadence, not a live stream.
- **Hypothesis:** Band 9 SpO₂ is historical/periodic; real-time SpO₂ is unlikely
  without a dedicated measurement session.

## 3. HRV

- HRS flags `0x06` contain no RR intervals, so HRV cannot be computed from the
  verified stream.
- Device-internal HRV exists in TruSleep/stress features.
- Band 10 live RRI route: `svc=0x19`, `cmd=0x01` with `hr_type=3`, notifications
  on `cmd=0x05`, about 50–70 s of RRI/SQI.
- **Hypothesis:** Band 9 may support the same route; unverified.

## 4. Steps / activity / sleep / stress

- All are expected to be historical, minute-level records in the fitness data
  service (`0x07`), parsed by Gadgetbridge.
- Sleep stages are device-internal (TruSleep); Huawei Health may add app-side
  scores.
- None are available from HRS.

## 5. Skin temperature

- Gadgetbridge has a skin-temperature measurement setting request.
- Device support is model-dependent; Band 9 support is unverified.
- If present, it is likely periodic/historical, not a live stream.

## 6. Sampling intervals

| Metric | Known control | Interval |
|---|---|---|
| HRS HR | none (standard) | ~1 Hz fixed |
| Automatic HR | on/off `0x07/0x17` | firmware-controlled |
| Continuous HR | on/off `0x07/0x1C` | firmware-controlled |
| Automatic SpO₂ | on/off `0x07/0x24` | firmware-controlled |
| Live HR/RRI | `0x19/0x01` (Band 10 evidence) | rate unknown |
| Workout HR | workout start | rate unknown |

Huawei Health 11.0.0.517's command builders were inspected directly. The
continuous-HR and automatic-SpO₂ commands carry a single enable/status byte.
No seconds/minutes interval TLV is present. The app's Smart/Real-time choice
selects a mode, not a numeric cadence.

**No public implementation, and not Huawei Health itself, exposes a configurable
HR/SpO₂ sampling interval.** Any claim of "aggressive intervals" must wait for a
captured command that actually carries an interval parameter. The likely reality
is that cadence is decided by the band firmware to balance battery and signal
quality.

## 7. 24×7 implications

- HRS gives 24×7 HR **if** the broadcast mode survives reboot/charging. It
  currently survives screen-off and disconnect; reboot/charging is untested.
- Proprietary continuous HR could remove the manual toggle, but requires auth.
- SpO₂/HRV/steps/sleep require proprietary sync; they cannot be acquired from
  HRS alone.
- Battery life will degrade with more frequent optical measurements; the band's
  firmware may override host requests to protect battery.

## 8. What "verified" means here

A metric is verified only when:

1. The independent client receives it from the physical band.
2. The payload is decoded by a unit-tested parser.
3. The value is compared with the band/Huawei Health display.
4. The timestamp and unit are recorded.

Everything else in this matrix is a hypothesis or an extrapolation from a
sibling device.
