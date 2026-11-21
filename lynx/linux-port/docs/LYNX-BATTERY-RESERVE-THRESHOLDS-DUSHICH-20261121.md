# Lynx Battery Reserve — Real Thresholds vs Evaluator Bands (D9)

- **Author**: Dushich (D9, per Gwyn round-5 queue, note #148)
- **Date**: 2026-11-21
- **Scope**: `lynx/linux-port/lynx-battery-reserve.sh` (repo), the guard actually running on Lynx, and the `lynx/tools/health` evaluator bands. Every claim is labelled **[VERIFIED]** (source read or live read-only check, cited), **[LIVE-VERIFIED]** (observed on Lynx today, read-only), or **[PROPOSED]** (evaluator policy, no source or trial backing).
- **Method**: repo source read; read-only Lynx checks via the pinned SSH route (service list, running PID, `sha256sum`, full `cat` of the installed script); offline diff of installed vs repo script. No writes, no install.

## Headline finding

**The repo script is NOT the behavior on Lynx.** [LIVE-VERIFIED] the installed guard
(`/usr/libexec/lynx-battery-reserve.sh`, sha256 `57a7936a…` via Lynx) differs from the repo
(`lynx/linux-port/lynx-battery-reserve.sh`, sha256 `390eb189…`): the repo file is a **newer,
not-yet-deployed** revision with charging-aware hold, a 40.0 °C shutdown, and a critical-10 cutoff
that the running guard does not have.

## 1. LIVE guard on Lynx [LIVE-VERIFIED, 2026-11-21]

Running: `/bin/sh /usr/libexec/lynx-battery-reserve.sh --watch` (PID 20080 at check time).
Service: `/etc/init.d/lynx-battery-reserve` ("Lynx unplugged battery reserve guard").

| Parameter | Value | Where |
| --- | --- | --- |
| Source | `/sys/bus/i2c/devices/7-0055/battery_snapshot`, identity `42495`, `capacity_error=0` required | installed script `read_capacity()` |
| CUTOFF | **20 %** | `CUTOFF=20` |
| INTERVAL | **30 s** samples | `INTERVAL=30` |
| Action 1 | capacity ≤ **20 %** for **3 consecutive samples (90 s)** → shutdown, reason `low_capacity` | watch loop |
| Action 2 | gauge read failed **3 consecutive samples (90 s)** → shutdown, reason `gauge_unavailable` | watch loop |
| Shutdown path | stdout + `/dev/kmsg` + `openrc-shutdown --poweroff now`, then `poweroff -f` after 15 s | `request_shutdown()` |
| NOT present | temperature check, charging/current logic, critical cutoff, charge-hold | (absent from installed script) |

Boundary semantics [VERIFIED from installed source]: trigger is `capacity -le 20` — **exactly 20 % is shutdown-eligible**. The live guard does not distinguish charging from discharging at all.

## 2. Repo guard (newer revision) [VERIFIED from source, NOT deployed]

`lynx/linux-port/lynx-battery-reserve.sh` adds (absent in the live script):

| Parameter | Value | Effect |
| --- | --- | --- |
| CRITICAL_CUTOFF | 10 % | capacity ≤ 10 → immediate shutdown `critical_capacity` (checked before charging branch) |
| CHARGE_TEMP_MAX | **40 000 m° = 40.0 °C** | gauge temperature ≥ 40.0 °C → immediate shutdown `charging_temperature` (checked first) |
| CHARGE_CURRENT_MIN | +50 mA | "charging" requires `gauge_current_ma_signed ≥ 50` |
| MAX_HOLD_SAMPLES | 240 × 30 s = **2 h** | at ≤ 20 % while "charging" without progress for 2 h → shutdown `no_charge_progress` |
| Sample validation | identity 42495 + all three `*_error=0`, current within ±32768, temp ≤ 60 000 m° | stricter `read_battery()` |

Check order in `--watch`: temperature → critical capacity → (reset) → charging/hold → low → gauge-failed.

## 3. Evaluator bands (`lynx/tools/health/portable_health.py`) [PROPOSED unless noted]

| Check | Band | Label |
| --- | --- | --- |
| battery `cap < 20` → **fail** | matches CUTOFF=20 (both live and repo guards) | **consistent with [LIVE-VERIFIED] guard**, but see boundary F2 |
| battery `20 ≤ cap < 35` → **warn** "trial-recheck band" | no source in either guard | **[PROPOSED]** |
| battery `cap ≥ 35` → ok | no source in either guard | **[PROPOSED]** |
| battery gauge errors > 0 → ≥ warn | advisory; live guard's action for 3 failed reads is **shutdown** | **[PROPOSED]**, deliberately softer than the live action |
| thermal `≥ 43 °C` warn, `≥ 50 °C` fail (machine `max_c`) | live guard has **no** temperature action; repo guard shuts down at **40.0 °C** (gauge sensor) | **[PROPOSED]** — mismatch if repo guard deploys (F4) |

## Findings

- **F1 [LIVE-VERIFIED]** Repo source ≠ live behavior; the repo file is an un-deployed revision. Any doc that cites `lynx/linux-port/lynx-battery-reserve.sh` as "the installed guard" overstates what is on the phone. Deployment of the newer revision is Aria's decision.
- **F2 [VERIFIED]** Off-by-one at 20 %: the live guard triggers at `capacity ≤ 20` (inclusive), the evaluator fails only at `cap < 20` and calls exactly 20 % a warn. At exactly 20 % the phone is shutdown-eligible while the board shows warn.
- **F3 [PROPOSED]** The 20–35 % warn band and the ≥ 35 % ok band are trial-recheck policy, not derived from either guard. Fine as policy; label them as such everywhere.
- **F4 [VERIFIED vs PROPOSED]** Thermal mismatch: the repo guard's 40.0 °C shutdown (battery gauge) is stricter than the evaluator's 43 °C warn on machine `max_c` (different sensors too). If the repo revision is deployed, a 40–43 °C battery gauge would power the phone off while the health board says ok.
- **F5 [VERIFIED]** Gauge-failure semantics differ by design: live guard shuts down after 3 failed reads (90 s); evaluator downgrades to warn on any gauge error. Keep, but the docstring should say the guard *powers off*, not merely "degrades evidence".
- **F6 [LIVE-VERIFIED]** The live guard's "even while charging" nuance in the evaluator docstring (`portable_health.py` "power off at 20%, even while charging") matches the live guard only trivially: the live guard has no charging branch at all — it powers off at ≤ 20 % regardless. The charging-aware behavior exists only in the un-deployed repo revision.

## Recommendation (for Aria — no action taken)

1. Decide deployment of the repo revision (it is the safer guard: 40 °C + charging-hold + critical-10).
2. If deployed: align the evaluator thermal band with the 40.0 °C action (or explicitly document the sensor difference) and fix the 20 % boundary (evaluator `cap ≤ 20` → fail).
3. Keep the 35 % recheck band labelled as a proposal pending a power trial.

## Evidence (all read-only, 2026-11-21)

```
Lynx:  ls /etc/init.d | grep -i battery   → lynx-battery-reserve (+ lynx-bluetoothd.before-battery-guard v1/v2)
Lynx:  ps | grep battery-reserve          → 20080 root /bin/sh /usr/libexec/lynx-battery-reserve.sh --watch
Lynx:  sha256sum /usr/libexec/lynx-battery-reserve.sh → 57a7936af54fc1a73b2671ef128536a2eee3718efb9640597f627649ef0ebed4
Nexus: sha256sum lynx/linux-port/lynx-battery-reserve.sh → 390eb18980393d42c4c811abeaa0da279904699b62e98113267d177a2f3ee7bb
Nexus: diff <installed> <repo>            → 4 extra constants, read_battery() vs read_capacity(), charging/hold/temp/critical branches (see §1–§2)
```
