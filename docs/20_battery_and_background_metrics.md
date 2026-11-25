# 20 — Battery and Background Metrics while HR Broadcast Is On

**Date:** 2026-11-26
**Question:** Does the band broadcast battery percentage, and does it keep
recording sleep / sleep times / SpO₂ / other routine metrics in the background
while HR Data Broadcast is active?

---

## 1. Battery percentage

### 1.1 What is exposed over BLE

A read-only GATT enumeration of the live **HR broadcast endpoint** found **no
Battery Service and no Battery Level characteristic**:

```
00001800  Generic Access
00001801  Generic Attribute
0000180a  Device Information
0000180d  Heart Rate
00003802  Huawei vendor
0000e2cb  Huawei vendor
0000e2e3  Huawei vendor
0000fe86  Huawei Link
cc353442-be58-4ea2-876e-11d8d6976366  Huawei vendor
```

There is no `0x180F` (Battery Service) and no `0x2A19` (Battery Level). A direct
read of `0x2A19` returns `Characteristic not found`.

The normal endpoint’s previously captured GATT map also has no `0x180F`
(`docs/02_ble_recon.md` §3). Battery is not a standard BLE service on either
identity.

### 1.2 Vendor characteristics

The four unknown vendor characteristics with a `read` property were read
read-only:

| Characteristic | Result |
|---|---|
| `1A19` (service `E2CB`) | `Read Not Permitted` |
| `E2E5` (service `E2E3`) | `Read Not Permitted` |
| `4A02` (service `3802`) | `Read Not Permitted` |
| `C551C36A-…` (service `CC353442`) | `Read Not Permitted` |

GATT reads are rejected without the authenticated/proprietary session. The
project’s HiChain3 authentication is unresolved for an independent client, so
the PC cannot currently read battery directly.

### 1.3 Practical consequence

Battery must currently be read from one of:

1. the band’s own battery indicator / Settings screen,
2. Huawei Health on the phone,
3. an authenticated proprietary session (not available independently yet).

### 1.4 Manual battery logging (implemented)

Because the measurement that matters is **drain rate while broadcasting**, the
dashboard now has a **Band battery (manual)** panel:

- enter the percentage shown on the band,
- optionally add a note (for example `broadcast on, 2 h`),
- the reading is stored as a `battery_reading` event in `device_events`,
- the panel shows the latest reading and, once two readings span at least one
  hour, the observed **%/hour and %/day** rate.

This uses the existing events table (no schema migration) and is available at
<http://127.0.0.1:8787>. Example:

```
Last: 82% at 26 Nov 2026, 01:10:00 IST · −0.45 %/h (−10.8 %/day) over 5.2 h
```

A negative sign means drain; a positive sign means charging.

## 2. Sleep, SpO₂ and other routine metrics

### 2.1 What HRS carries

The standard Heart Rate Service carries only heart rate. It has no sleep,
SpO₂, stress, steps, activity, or battery fields. The verified HRS stream is
one notification per second with a uint8 BPM and a contact bit.

### 2.2 What the band stores internally

The project’s authenticated captures show that the band does maintain
proprietary health records:

- `0x07/0x0B` minute-record envelopes (HR/status records, partially decoded),
- `0x07/0x0D` status-record envelopes,
- `0x2C/0x01` file requests for `sequence_data`, `rrisqi_data.bin`, `spo2.bin`,
  and related files,
- `spo2.bin` (8,694 bytes) contains periodic PPG/OSA records; the recovered file
  has records dated 17–18 Nov 2026 at roughly 30–60 minute spacing,
- `rrisqi_data_h5/h6.bin` (114 bytes each) contain RRI/SQI records from
  25 Nov 2026 around 16:26–16:27 UTC.

These records prove the band **has** an internal sleep/SpO₂/PPG store and a
file-transfer service. They do **not** yet prove that recording continues while
HR Data Broadcast is active: the recovered `spo2.bin` predates the broadcast
experiments, and the RRI files were produced around a band Heart-rate screen
session.

### 2.3 Why the PC cannot read them directly now

The normal endpoint is not advertised while HR Data Broadcast is active, and
the proprietary history/file services require the authenticated FE86 session.
The HR endpoint’s vendor characteristics are read-protected. There is no
standard GATT service for sleep or SpO₂.

Therefore the PC can currently observe **heart rate only** while broadcasting.
Sleep/SpO₂ availability must be checked through Huawei Health after broadcast
is turned off, or through an authenticated capture.

### 2.4 Definitive experiment

Run this over one night (or two consecutive nights):

**Phase A — broadcast off (baseline)**

1. Turn HR Data Broadcast off.
2. Wear the band normally overnight.
3. Sync Huawei Health in the morning.
4. Record: sleep duration/stages, SpO₂ samples (automatic), stress, steps,
   resting HR, and battery percentage before/after.
5. Log the battery readings in the dashboard.

**Phase B — broadcast on, PC connected**

1. Turn HR Data Broadcast on and leave the daemon connected overnight.
2. The phone cannot sync during this phase because the normal endpoint is not
   advertised; that is expected.
3. In the morning, log the band battery percentage before turning broadcast off.
4. Turn HR Data Broadcast off, open Huawei Health, sync.
5. Check whether sleep stages/duration, SpO₂, stress and steps for the B night
   are present and timestamped during the broadcast period.

**Phase C — broadcast on, PC not connected (optional)**

Repeat B for one night with the daemon paused, so the band is advertising but
no central is connected. This separates “broadcast mode” from “active BLE
connection” effects.

**Interpretation**

- If B/C show sleep and SpO₂ records for the broadcast period, the firmware
  continues routine recording while broadcasting; the PC database remains the
  HR record and Health remains the sleep/SpO₂ record.
- If B/C show no records for that period, broadcast mode suppresses some
  background metrics; the 24×7 design must then choose between continuous HR
  and those metrics, or use the authenticated proprietary path.
- Compare battery drain A vs B vs C using the manual battery log. This is the
  only reliable way to answer the battery-impact question on this firmware,
  because battery is not exposed over the unauthenticated BLE interface.

### 2.5 What would make this automatic

- **Battery:** authenticated FE86 command or an Android relay using the paired
  Huawei Health session.
- **Sleep/SpO₂/history:** authenticated `0x07`/`0x2C` sync (HiChain3) or a
  Health export/relay. The file-transfer format is partially known; the
  remaining work is authentication and record decoding, not GATT discovery.

Until then, the dashboard records HR continuously and accepts manual battery
readings, and the analysis application remains read-only.
