# 19 — 10-Minute Connection Endurance Test

**Date:** 2026-11-26
**Duration:** 600.2 s
**Host:** Fedora, BlueZ, IMC Networks Bluetooth Radio (hci0)
**Band:** Huawei Band 9 / `HUAWEI Band HR-TEST`, HR Data Broadcast active
**Result:** **all injected faults recovered automatically; no manual service
restart was required.**

---

## 1. Fault schedule

The test ran for 10 minutes and injected the failures that can be triggered
from the host. HR Data Broadcast on/off is band-side and is covered separately.

| t (s) | Injected fault |
|---|---|
| 30 | Adapter powered off for 10 s, then on |
| 120 | Acquisition paused for 10 s, then resumed |
| 210 | Daemon `SIGKILL` (systemd restart) |
| 300 | Adapter powered off for 15 s, then on |
| 390 | Web service restarted |
| 450 | BLE link forcibly disconnected with `bluetoothctl disconnect` |
| 510 | Acquisition paused for 5 s, then resumed |
| 570 | Adapter powered off for 5 s, then on |
| 600 | End of observation |

## 2. Recovery results

| Injected fault | Recovery to `connected` | Notes |
|---|---:|---|
| Adapter off 10 s | **10.0 s** | after power-on, HR 82 |
| Pause 10 s | **2.5 s** | link released and re-established |
| `SIGKILL` | **5.1 s** | new systemd PID, HR 88 |
| Adapter off 15 s | **4.5 s** | after power-on, HR 86 |
| Web restart | **0 s** | acquisition PID unchanged (`independent=true`) |
| Forced link drop | **2.3 s** | HR 88 |
| Pause 5 s | **2.5 s** | link released and re-established |
| Adapter off 5 s | **2.0 s** | after power-on, HR 85 |

The `SIGKILL` recovery also produced a `stale_link_cleared` event: the new
process found BlueZ still holding the old HR link, released it, and reconnected.
This is the exact failure that previously caused the permanent “will not
reconnect” loop.

## 3. Quality during the run

| Metric | Value |
|---|---|
| Samples connected | **526 / 599 (87.8%)** |
| Disconnect transitions | 7 |
| Measurements stored in window | **515** |
| HR min / median / max | **70 / 84 / 108 bpm** |
| Disconnect events | 4, all `reason=disconnected` |
| Time since last packet at each drop | **0.33–0.79 s** |
| Gaps > 5 s | 6 |
| Longest gap | **20.6 s** (15 s adapter-off + recovery) |
| Kernel `hci0 Opcode 0x2005 failed: -16` | **0** |
| Adapter re-initialisations | 3 (the three deliberate power cycles) |
| Final state | connected, HR 85, session 22 |

The 12.2% non-connected time is almost entirely the deliberate 10 + 15 + 5 s
adapter-off windows, the 10 + 5 s pause windows, the kill/restart interval, and
the reconnect backoff. Missing intervals are absent from the database; they are
not zero-filled or interpolated.

## 4. Failure events observed

| Event | Count |
|---|---:|
| `connected` | 7 |
| `disconnected` | 4 |
| `adapter_powered_off` | 3 |
| `error` | 7 |
| `monitoring_paused` | 2 |
| `monitoring_resumed` | 2 |
| `session_interrupted` | 1 |
| `stale_link_cleared` | 1 |
| `monitoring_started` | 1 |
| `process_start` | 1 |

Failure codes sampled from the dashboard: `link_dropped` and
`adapter_powered_off`. No `bluez_discovery_stuck`, no `adapter_unavailable`, and
no `adapter_reset` was needed during this run.

## 5. What this proves and what it does not

**Proved**

- Adapter power loss is detected without a crash loop and recovers when the
  adapter returns.
- A killed daemon is restarted by systemd, the open session is marked
  `interrupted`, and the stale BlueZ link is released before reconnecting.
- A forced BLE link drop is detected and reconnected in ~2 s.
- The web process is fully independent of acquisition.
- Pause/resume releases and reacquires the link correctly.
- The pre-connect discovery cleanup eliminated the `hci0` `EBUSY` errors seen
  before the fix.

**Not covered by this run**

- HR Data Broadcast manually turned off/on during the 10 minutes. This was
  exercised earlier: the daemon records `hr_broadcast_off`, shows the band as
  nearby with broadcast OFF, and reconnects after the user starts broadcast.
- A phone/Huawei Health takeover, out-of-range movement, or band power-off.
  These are band-side decisions; the handler treats them as link drops or
  missing advertisements and keeps retrying.
- A full host reboot (systemd lingering is enabled; boot recovery still needs a
  separate reboot test).

## 6. Reproduce

The fault schedule is host-destructive (it power-cycles the adapter) and must
only be run when no other Bluetooth device is connected. The test checks
`bluetoothctl devices Connected` and skips an adapter cycle if another device
is present.

```bash
# Start a 10-minute run with:
#   adapter off/on: 30 s, 300 s, 570 s
#   pause/resume:   120 s, 510 s
#   SIGKILL:        210 s
#   web restart:    390 s
#   link drop:      450 s
```

The generated artifacts are local and gitignored:

- `endurance-report.md`
- `endurance-report.json`
- `endurance-samples.json`
- `endurance-timeline.json`
