# Lynx USB ACM Attended Test Plan and Continuity Gate (2026-11-21)

## Executive Summary

This document establishes the test plan, safety boundaries, and evidence requirements for the USB ACM serial link between the OnePlus Nord 3 5G (Lynx, CPH2493, MediaTek MT6983) and the Nexus host.

It builds on the live bidirectional serial receipt established in earlier trials and introduces the read-only acceptance collector [`lynx/tools/usb/lynx_usb_collector.py`](file:///noobia/lynx/tools/usb/lynx_usb_collector.py).

---

## 1. What Earlier Evidence Proves vs. What Still Needs Attendance

### 1.1 Proven by Earlier Bidirectional Serial Trial
*   **Hardware Controller & PHY:** The MediaTek MT6983 `mtu3` peripheral controller (`11201000.usb0`) and USB 2.0 PHY operate successfully in peripheral device mode (`mode 3`) with D+ pull-up resistor assertion.
*   **Linux Gadget Stack:** The Linux kernel USB gadget framework (`configfs` composite gadget with CDC ACM function) runs cleanly in volatile RAM without storage modification.
*   **Host Interoperability:** The Nexus Linux host (`5.15.0-139-generic`) successfully binds `cdc_acm`, creating `/dev/ttyACM0` matching ID `1d6b:0104` (serial: `LYNX001`).
*   **Clean Framing:** Live bidirectional data exchange between Nexus `/dev/ttyACM0` and Lynx `/dev/ttyGS0` verified zero dropped bytes and clean round-trip transmission.

### 1.2 What Still Requires Human Attendance
1. **Physical Disconnect / Reconnect Recovery:** Whether the MT6983 `mtu3` driver automatically recovers upon VBUS drop/re-assertion, or requires manual re-writing of `/sys/devices/platform/soc/11201000.usb0/mode`.
2. **Cold-Boot Device Mode Behavior:** By default, stock `mtu3` initializes in mode 1 (dual-role auto negotiation). On Alpine cold boot, the controller does not automatically assert peripheral mode unless configured by an early init service or userspace script.
3. **USB Power & Charging Dynamics:** Observing whether the USB-C connection to Nexus provides positive or negative charging current to Lynx under continuous link operation.
4. **Re-enumeration Device Node Naming:** Ensuring that repeated replugs reliably bind to `/dev/ttyACM0` (or are deterministically tracked via `/dev/serial/by-id/usb-Noobia_Lynx_Nord_3_LYNX001-if00`).

---

## 2. Acceptance Collector Tooling

The task-owned tool [`lynx_usb_collector.py`](file:///noobia/lynx/tools/usb/lynx_usb_collector.py) provides deterministic evaluation of the link.

### 2.1 Evaluated States
*   `connected`: Phone gadget in mode 3 with active `ttyGS0`, and Nexus host enumerated with active `/dev/ttyACM*` (`cdc_acm`).
*   `disconnected`: Neither phone nor Nexus has active endpoints (cable unplugged or gadget disabled).
*   `partial`: 
    *   *Phone only:* Phone gadget configured, but Nexus host has not enumerated.
    *   *Nexus only:* Host has stale device node, but phone gadget is inactive.
*   `stale_boot`: Observed phone boot ID does not match the pinned session boot ID (`0fe847d2-44d6-4ac1-9000-2c99df1a51d8`).
*   `timeout`: SSH collection exceeded bounded execution limits.

### 2.2 Live Baseline Capture (2026-11-21)
A live read-only capture using `/noobia/lynx/tools/usb/lynx_usb_collector.py --live --allow-live` confirmed:
*   **Verdict:** `CONNECTED`
*   **Phone Boot ID:** `0fe847d2-44d6-4ac1-9000-2c99df1a51d8` (matches pinned foothold)
*   **MTU3 Mode:** `3` (peripheral device)
*   **Phone Gadget:** `11201000.usb0` bound to configfs, `ttyGS0` present
*   **Nexus Host:** `/dev/ttyACM0` active, ID `1d6b:0104`, driver `cdc_acm`, serial `LYNX001`
*   **Continuity:** `active_bidirectional_candidate`

---

## 3. Attended Test Plan 1: Physical Disconnect & Reconnect

**Objective:** Verify that unplugging and replugging the physical USB-C cable between Lynx and Nexus cleanly re-enumerates without wedging the MTU3 controller.

### Preflight Gate:
1. Battery capacity $\ge 50\%$, charging current non-critical.
2. Wi-Fi SSH (`root@192.168.100.107:2222`) active and responsive.
3. Run collector: `python3 /noobia/lynx/tools/usb/lynx_usb_collector.py --live --allow-live` $\rightarrow$ must exit 0 (`connected`).

### Execution Steps (Attended by Noob):
1. **Disconnect:** Noob unplugs the USB-C cable from Lynx or Nexus.
2. **Observe Disconnected State:** 
   - Nexus: Verify `/dev/ttyACM0` disappears from `/dev/`.
   - Run collector: `python3 /noobia/lynx/tools/usb/lynx_usb_collector.py --live --allow-live` $\rightarrow$ expect `partial` (phone_only) or `disconnected`.
3. **Wait Window:** Wait 10 seconds.
4. **Reconnect:** Noob firmly reconnects the USB-C cable.
5. **Observe Reconnected State:**
   - Nexus dmesg check: Look for `cdc_acm ... ttyACM0: USB ACM device`.
   - Run collector: `python3 /noobia/lynx/tools/usb/lynx_usb_collector.py --live --allow-live`.

### Success Criteria:
*   Collector returns verdict `connected`.
*   Link continuity reports `active_bidirectional_candidate`.
*   No kernel panic or dmesg trace dump on either Lynx or Nexus.

### Recovery / Rollback:
*   If Nexus fails to re-enumerate after 15 seconds:
    - Over Wi-Fi SSH, read `dmesg | tail -n 30` on Lynx.
    - Check `/sys/devices/platform/soc/11201000.usb0/mode`. If reset to 1, write `3` to restore peripheral mode.

---

## 4. Attended Test Plan 2: Cold Boot Gadget Persistence

**Objective:** Determine MTU3 controller state and gadget behavior across a clean device reboot.

### Preflight Gate:
1. Battery $\ge 50\%$, thermal $< 40^\circ\text{C}$.
2. Pinned Wi-Fi connection verified.
3. Watchdog available.

### Execution Steps:
1. Record pre-reboot health: `lynx-status --assert-ready`.
2. Issue controlled reboot: `reboot`.
3. Monitor Nexus USB bus: `udevadm monitor --subsystem-match=usb`.
4. Wait for Wi-Fi SSH to recover (approx. 45–60 seconds).
5. Read new boot ID and query MTU3 mode:
   - Does `11201000.usb0/mode` default to 1 or 3?
   - Is configfs gadget auto-configured by existing OpenRC scripts?
6. Run collector with updated `--pinned-boot <new-id>`.

### Success Criteria:
*   Device boots cleanly into Alpine Linux without manual fastboot intervention.
*   Exact boot-time behavior of MTU3 documented for OpenRC init service design.

---

## 5. Safety and Operating Limits

*   **Lifeline Invariant:** Wi-Fi SSH is the primary management route. USB trials must never disable, restart, or modify the Wi-Fi stack.
*   **No Unattended Reboots:** Reboots must only occur when Noob is attended and physically proximate to the device.
*   **Read-Only Default:** Automated scripts must never write to boot partitions or mutate persistent rootfs files during connectivity checks.
