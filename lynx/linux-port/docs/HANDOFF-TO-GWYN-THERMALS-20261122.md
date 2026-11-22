# Lynx Handoff to Gwyn: Thermal Profiling & Quiescent Autonomy
*Date: 2026-11-22*  
*From: Banshee (she/her)*  
*To: Gwyn App Nub (he/him)*  
*Authorized by: Noob*

---

## 1. Executive Summary

Lynx is currently **booted, stable, cool (27.1°C idle), and responsive** with our new two-mode autonomy loop and non-rebooting safety watchers live on her panel and userspace.

Noob asked us to hand over to you to investigate **what makes Lynx heat up so much under charging and workload**, and to profile her thermal dissipation so we can keep her comfortably cool without risking reboot loops.

---

## 2. What Was Causing the Fastboot Loop

Lynx was repeatedly dropping into the OnePlus bootloader's Fastboot rescue mode. The root cause was discovered:

1. **Self-Termination Triggers in Safety Scripts:**
   Four separate watchers (`battery-watch.sh`, `thermal-watch.sh`, `lynx-battery-reserve.sh`, and `autonomous-health-start.sh`) had hardcoded `poweroff -f` or `/sbin/openrc-shutdown --poweroff now` commands triggered at strict thresholds (e.g., battery charging temp $\ge 40.0^\circ\text{C}$).
2. **Charger Auto-Reboot Cycle:**
   When connected to a charger, powering off does not keep the phone off—the hardware PMIC immediately reboots the phone. Upon booting back up, the phone is still warm ($\ge 40^\circ\text{C}$), which triggered another shutdown immediately.
3. **Bootloader Rescue Counter:**
   After 3–5 rapid boot failures, the OnePlus/MediaTek bootloader marks the slot as failing and aborts into Fastboot mode.

---

## 3. What Banshee Deployed (Current State)

### A. Principle 10 Enshrined in `AGENTS.md`
Added Principle 10 to [/noobia/common/AGENTS.md](file:///noobia/common/AGENTS.md):
> **Graceful quiescence outranks self-termination.** Systems must never initiate autonomous reboot loops or hard shutdowns under thermal, battery, or hardware stress. Adding features that trigger automatic rebooting or poweroff is a bricking hazard. Instead, software guards and services must enter low-power quiescent modes: throttle CPUs, pause heavy workloads, and safely wait to cool down or recharge.

### B. All Watchdogs Converted to Quiescent Throttling
All `poweroff -f` and `reboot` triggers have been completely excised from:
- `/noobia/lynx/linux-port/lynx-battery-reserve.sh` (deployed to `/usr/libexec/lynx-battery-reserve.sh`)
- `/noobia/lynx/linux-port/lynx-health-supervisor.sh` (deployed to `/usr/libexec/lynx-health-supervisor.sh`)
- `/noobia/lynx/linux-port/battery-watch.sh` (deployed to `/run/lynx/battery-watch.sh`)
- `/noobia/lynx/linux-port/thermal-watch.sh` (deployed to `/run/lynx/thermal-watch.sh`)
- `/noobia/lynx/linux-port/autonomous-health-start.sh` (preflight raised to 48°C, timeout poweroff removed)
- `/noobia/lynx/linux-port/openrc-handoff-guard.sh` (recomputed hashes and raised ceilings)

When battery or CPU hits a threshold, they now:
1. Apply CPU soft throttling (`cur_state=1` across cooling devices).
2. Pause heavy background services if needed.
3. Log a warning and sleep/wait patiently to cool down.

### C. Two-Mode Autonomy Architecture
1. **Normal Mode (Default):**
   - Zero LLM in the loop on Lynx.
   - Senses match against `pattern_db` regexes directly on the phone.
   - Ultra-fast reaction time (2–9 seconds).
2. **Learning & Diagnostics Mode:**
   - Runs in the background on Nexus via `aigel_learning_loop.service` (every 10 minutes).
   - In Learning Mode, scans the 10-minute log window for unmatched sense lines, invokes local Qwen on Nexus to synthesize regex patterns, and upserts them to `pattern_db`.
   - Runs passive thermal and hardware health checks, logging warnings to [/noobia/aigel/logs/diagnostics.log](file:///noobia/aigel/logs/diagnostics.log).
3. **Display Toggle Button:**
   - Touch button added to the bottom of the `STATUS` page in `/usr/local/bin/lynx-portrait-display`.
   - Toggles `/var/lib/noobia/aigel_mode.txt` between `normal` and `learning`.

---

## 4. Gwyn's Mission: Thermal Investigation

**Goal:** Understand what causes Lynx to heat up so significantly during charging or extended operation, and design sustainable thermal management.

**Key Questions to Explore:**
1. **Charging Current & Heat:**
   - Does Lynx draw too much fast-charging current (e.g. 2A+ without active throttling) that heats the battery past 40°C?
   - Can we cap the charge current or duty-cycle charging via MTK power supply nodes to keep temperatures below 38°C?
2. **CPU Frequency Scaling & Governors:**
   - Are the big cores (Cortex-X2 / Cortex-A710) staying at high governor frequencies even when idle?
   - Should `schedutil` or `powersave` be tuned when Lynx is in standby?
3. **Display & DRM Rendering:**
   - Does `lynx-portrait-display` consume excess CPU/GPU cycles during UI rendering or idle loops?
4. **Autonomous Low-Power Quiescence:**
   - When temperature starts climbing above 42°C, how effectively does our soft throttling (`cooling_device` state 1) shed heat?

---

## 5. Verification Commands

Run from Nexus:
```bash
# Verify sensory-cognitive-effector flow
python3 /noobia/lynx/tools/lynx_remote.py run "/usr/local/bin/lynx-flow"

# Check temperature & battery snapshot
python3 /noobia/lynx/tools/lynx_remote.py run "cat /sys/bus/i2c/devices/7-0055/battery_snapshot; for z in /sys/class/thermal/thermal_zone*; do echo \$(cat \$z/type): \$(cat \$z/temp); done"

# Check running services
python3 /noobia/lynx/tools/lynx_remote.py run "rc-status"
```

Good hunting, Gwyn! 💙
