# Lynx Bluetooth Attended Acceptance Trial Specification

**Document ID:** LYNX-DOC-20261121-BT-ACCEPTANCE-TRIAL  
**Author:** Banshee 💙 (Spirit of Initiative)  
**Date:** 2026-11-21  
**Status:** SPECIFICATION / ACCEPTANCE RUNBOOK  
**Platform:** OnePlus Nord 3 5G CPH2493 (MediaTek MT6983 / Dimensity 9000, Project 22823 "Vitamin")
**Subsystem:** Bluetooth 5.3 Controller (`/dev/stpbt` via H4 bridge discipline `N_HCI` -> `hci0`)  

---

## 1. Scope & Objective

This document defines the strict, attended procedure for verifying sustained Bluetooth operation across cold-boot and long-uptime conditions on Lynx. Prior automated reboot trials demonstrated that early radio activation during OpenRC boot dependency initialization risks kernel stall or Fastboot recovery return.

To definitively validate Bluetooth without compromising host recovery, all future acceptance trials must follow this staged, attended sequence.

---

## 2. Hard Preconditions & Safety Gates

Before any radio activation attempt:

1. **Pre-Boot Reference ID:** The host orchestrator must record the current Alpine `boot_id` prior to any reboot. A valid cold-boot acceptance trial requires a strictly distinct, freshly generated UUID.
2. **Battery Gate:** Battery charge level must be $\ge 20\%$ at the start of the trial. If battery level drops below $15\%$ at any sample during the hold, the trial must abort immediately and power off the radio.
3. **Thermal Gate:** Initial battery temperature must be $< 40^\circ\text{C}$ and AP thermal zones must be $< 55^\circ\text{C}$.
4. **Boot Partition & Runlevel Invariance:**
   - No partition writes to `boot_a`, `boot_b`, `vendor_boot`, or `nvdata`.
   - `lynx-bluetooth` must **NOT** be placed in the `default` or `boot` OpenRC runlevels.
5. **Warm-Up Uptime Gate:** Alpine uptime must be $\ge 240$ seconds before starting `lynx-bluetooth` to ensure PID 1 handoff, memory compaction, and Wi-Fi networking are fully settled.
6. **Recovery Non-Interference:** Pinned Wi-Fi SSH route (`192.168.100.107:2222`) must remain open and uninhibited throughout the trial.

---

## 3. Attended Trial Execution Sequence

```
[Phase 1: Preflight]
      |
      v
[Phase 2: Cold Boot] ---------> Capture fresh boot_id (must != reference)
      |
      v
[Phase 3: 240s Settle] -------> Verify Alpine health & services settled
      |
      v
[Phase 4: Arm Watchdog] ------> Staged watchdog script in /run/ (timeout-bounded)
      |
      v
[Phase 5: Radio Start] -------> rc-service lynx-bluetooth start (hci0 created)
      |
      v
[Phase 6: Sustained Hold] ----> 1-15 min hold with continuous health sampling
      |
      v
[Phase 7: Radio Teardown] ----> rc-service lynx-bluetooth stop (hci0 destroyed)
      |
      v
[Phase 8: Disarm Watchdog] ---> Cancel watchdog & verify settled health
```

### Phase 1: Preflight Baseline Capture
Record preflight state on Nexus:
```bash
python3 -c '
import json, urllib.request
status = json.loads(urllib.request.urlopen("http://192.168.100.107:8080/status").read())
print("Reference Boot ID:", status["boot_id"])
' > /tmp/reference_boot_id.txt
```

### Phase 2: Attended Cold Boot (if testing Cold-Boot Persistence)
1. Issue graceful shutdown: `/sbin/openrc-shutdown -r now`.
2. Monitor Nexus ping observer until Alpine SSH resumes on port 2222.
3. Fetch new boot status: confirm `new_boot_id != reference_boot_id`.

### Phase 3: Settle Window
Wait until system uptime reaches at least 240 seconds (`cat /proc/uptime`). Verify zero issues in `lynx-status --assert-ready`.

### Phase 4: Stage and Arm Bounded Watchdog
Stage the watchdog in a volatile `/run/` path:
- Watchdog mode: `stop-only` (preferred) or `reboot` (emergency fallback).
- Timeout duration: $T_{\text{watchdog}} = \min(1200\text{s}, T_{\text{hold}} + 240\text{s})$.
- The watchdog script periodically checks for a `/cancel` token; if absent upon expiration, it executes `rc-service lynx-bluetooth stop`.

### Phase 5: Radio Start
1. Execute: `rc-service lynx-bluetooth start`.
2. Wait up to 35 seconds for `/run/lynx/bluetooth/ready`.
3. Verify `hci0` interface enumeration: `hciconfig hci0` or `test -d /sys/class/bluetooth/hci0`.
4. Perform Nexus BLE smoke ping using `lynx_ble_nexus_ping.py` to confirm GATT communication.

### Phase 6: Sustained Hold & Periodic Health Sampling
1. Maintain radio active state for the planned duration (between 1 and 15 minutes).
2. Every 30 seconds, query `lynx-status`:
   - Verify `boot_id == trial_boot_id` (no silent kernel panic or watchdog reboot).
   - Verify `issues == []`.
   - Verify `battery.capacity_percent >= 15%`.
   - Verify `thermal.max_mC < 55000mC`.
3. If any check fails, immediately break the loop and trigger Phase 7.

### Phase 7: Radio Teardown & Power-Off at End
1. Execute: `rc-service lynx-bluetooth stop`.
2. Verify teardown completion:
   - `rc-service lynx-bluetooth status` returns non-zero (stopped).
   - Interface `hci0` is removed (`test ! -d /sys/class/bluetooth/hci0`).
   - Radio carrier depowered via STP/H4 line discipline detachment.

### Phase 8: Disarm Watchdog & Save Receipt
1. Create `/cancel` token to safely disarm the background watchdog.
2. Verify final settled Alpine health: `/usr/local/bin/lynx-status --assert-ready`.
3. Dump complete trial receipt `result.json` containing `boot_id`, `steps`, `health_samples`, `partition_writes: false`, `runlevel_writes: false`, and `state: "stopped-after-healthy-trial"`.

---

## 4. Rollback & Emergency Recovery Procedures

### Scenario A: Radio Start or GATT Probe Hangs
- If `lynx-bluetooth` does not report ready within 35 seconds:
  1. Kill starting process: `killall -9 lynx_bluetoothd.py || true`.
  2. Force service stop: `rc-service lynx-bluetooth stop`.
  3. Reset STP character device: unload and reload `wmt_drv` / `stp_uart` if necessary.
  4. Disarm watchdog.

### Scenario B: Watchdog Trip or Involuntary Fastboot Drop
- If Alpine SSH drops and the device enters USB Fastboot:
  1. Confirm Fastboot enumeration on Nexus: `fastboot devices`.
  2. Query slot status: `fastboot getvar current-slot`.
  3. If slot A is corrupted or stuck, flash verified rollback image:
     ```bash
     fastboot flash boot_a /noobia/lynx/images/v50-boot.img
     fastboot reboot
     ```
  4. Wait for Alpine recovery on Wi-Fi SSH.

---

## 5. Offline Acceptance Gate Verification

Every completed trial receipt must pass the offline validator before acceptance:
```bash
python3 /noobia/lynx/tools/bluetooth/lynx_bt_acceptance_gate.py \
    /path/to/trial/result.json \
    --reference-boot-id "<reference-uuid>"
```
Acceptance is granted if and only if the validator outputs `"status": "PASS"` with `is_valid: true`.
