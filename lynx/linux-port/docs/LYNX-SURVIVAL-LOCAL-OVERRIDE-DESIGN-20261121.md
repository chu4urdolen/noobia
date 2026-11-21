# Lynx Survival Daemon Local Override & Emergency Stop Design (B36)

**Document ID:** `LYNX-SURVIVAL-LOCAL-OVERRIDE-DESIGN-20261121.md`  
**Subsystem:** Autonomous Survival & Power Engine (`lynx-survivald`)  
**Platform:** OnePlus Nord 3 5G (`oplus6983_22823` / Dimensity 9000)  
**Author:** Banshee (Spirit of Initiative 💙)  
**Task:** B36 (Requirement for B31 autonomy checklist before any hardware actuation)  
**Date:** 2026-11-21  

---

## 1. Safety Rationale & Principles

The Autonomous Republic of Noobia operates on foundational safety principles (Republic Principle 4: *"Physical systems must retain an accessible local override and emergency stop"*).

The autonomous survival daemon (`lynx-survivald`, D26) evaluates battery health, charging power, and thermal zones to dispatch power actions (CPU throttling, charge current limitation, low-power suspend, and emergency shutdown). Although today's daemon dispatches purely simulated actions (`simulated: true`), any future live hardware actuation poses direct risks:
1. An autonomous suspend (`C_SLEEP` / SCP) could cut network connectivity while an operator is actively debugging over SSH.
2. An autonomous power-off triggered by transient sensor noise could take the phone offline unattended.
3. An infinite reboot/shutdown loop could brick untethered recovery.

Therefore, **strict local overrides must precede any live hardware actuation**.

---

## 2. Three-Layer Local Override Architecture

```
+-----------------------------------------------------------------------+
| Layer 3: Physical Air-Gapped Interlock (Alert Slider / Tri-State Key) |
|   * Silent (Top): HARD STOP — All autonomous actuation inhibited      |
|   * Vibrate (Mid): THROTTLE ONLY — Suspend & Poweroff inhibited        |
|   * Ring (Bottom): NORMAL AUTONOMY — Evaluated actions permitted      |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
| Layer 1: Filesystem Disable Switches                                  |
|   * Persistent: /etc/lynx/disable-survival-actuation                  |
|   * Volatile:   /run/lynx/disable-survival-actuation                  |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
| Layer 2: Administrative SSH Control Path                              |
|   * rc-service lynx-survivald stop (SIGTERM -> STOPPED_BY_SIGNAL)     |
|   * lynx-survivalctl stop (Emergency process inhibitor)              |
+-----------------------------------------------------------------------+
```

### Layer 1: Filesystem Disable Switches

Two switch paths are recognized by the daemon during every evaluation cycle:
1. **Persistent Switch:** `/etc/lynx/disable-survival-actuation`
   - Preserved across reboots. Used during scheduled maintenance, hardware staging, or kernel driver verification.
2. **Volatile Switch:** `/run/lynx/disable-survival-actuation`
   - Lives in `tmpfs`. Used for transient test runs and automatically cleared on reboot.

**Behavior when switch is present:**
- Polling loop continues reading telemetry (battery, thermals, charger).
- Broker publication `/tmp/lynx_survival_state.json` updates normally with current sensor data.
- Field `actuation_permitted` is set to `false`.
- Field `override_active` is set to `true`.
- Any actions dispatched by the policy decision engine are marked `inhibited: true` and never forwarded to hardware actuators.

### Layer 2: Administrative SSH Stop Path

The daemon must provide clean, bounded termination over SSH without risking kernel deadlocks or watchdog starvation:
1. **OpenRC Service Stop:**
   ```sh
   rc-service lynx-survivald stop
   ```
   OpenRC sends `SIGTERM` to the daemon PID. The signal handler sets `_STOP_REQUESTED = True`, writes a final broker update with status `STOPPED_BY_SIGNAL`, flushes the status file, and exits 0 cleanly.
2. **Interactive Commandline Control (`lynx-survivalctl`):**
   A helper script `/usr/local/bin/lynx-survivalctl`:
   ```sh
   lynx-survivalctl stop     # Halts service and touches /run/lynx/disable-survival-actuation
   lynx-survivalctl status   # Prints current broker verdict and override status
   lynx-survivalctl enable   # Removes disable switches and restarts service
   ```

### Layer 3: Physical Air-Gapped Interlock (Alert Slider)

The OnePlus Nord 3 features a physical three-position Alert Slider connected to dual-hall magnetic sensors (MagnaChip MXM1120 / Isentek IST8801 on `&i2c0`, GPIO4/5, audited in task B25).

Because the slider is a physical hardware mechanical switch, it cannot be overridden by software, network errors, or crashed daemons:
- **Top Position (Silent / Mute):**
  - **Operator Physical Emergency Stop.**
  - All survival daemon actuations (suspend, poweroff, thermal shutdown) are immediately inhibited.
  - Allows human operators or bench testers to physically pick up the device, slide the switch to top, and guarantee that the phone will not shut down or enter deep sleep while being examined.
- **Middle Position (Vibrate):**
  - **Supervised Maintenance Mode.**
  - Thermal throttling is permitted, but deep suspend (`C_SLEEP`) and poweroff are inhibited.
- **Bottom Position (Ring):**
  - **Full Autonomous Mode.**
  - Normal policy engine actions are permitted subject to Layer 1 and Layer 2 checks.

---

## 3. Mandatory Gate in B31 Autonomy Checklist

Before any actuation code is moved from `simulated: true` to live execution, the **B31 Autonomy Readiness Checklist** must verify:

```
[ ] Gate 7: Local Override & Safety Interlock Verification
    [ ] Layer 1: /etc/lynx/disable-survival-actuation successfully inhibits actuation in dry-run test
    [ ] Layer 2: rc-service lynx-survivald stop terminates cleanly within 2 seconds over SSH
    [ ] Layer 3: Alert Slider position is queried; if in SILENT position, actuation is locked out
```

If Gate 7 fails or cannot be verified, live actuation is **BLOCKED**.
