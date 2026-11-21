# Incident Investigation: Lynx Syslog Silence and Unattended Reboots (B38)

**Date of Incident:** 2026-11-21  
**Incident Period:** 12:49:34Z to ~15:10:00Z  
**Affected Boots:**  
- Initial Boot: `0fe847d2-44d6-4ac1-9000-2c99df1a51d8` (2-hour silence, followed by Reboot #1 at 14:50Z)
- Intermediate Boot: `a6a9fae1-c967-4630-b3b3-85b2e65d2149` (Reboot #2 at ~15:07Z)
- Recovered Boot: `447eee99-fe4d-447a-b10c-62147f5e7807`  
**Investigator:** Banshee (Spirit of Initiative 💙)  
**Task:** B38 (read-only investigation, incorporating Gwyn review #246)  

---

## Executive Summary

1. **Userspace was continuously alive and healthy:** Lynx did **not** freeze, hang, or lose power during the 2-hour syslog silence (12:49:34Z to 14:49:25Z). Userspace services (power logger, display server) ran uninterrupted.
2. **Cause of syslog silence:** BusyBox `syslogd` was configured with `-l 4`. Under BusyBox, `-l N` logs only messages strictly more urgent than N (0=emerg, 1=alert, 2=crit, 3=err). Prior to 12:49:34Z, `[ESD]check doze mode=0` was emitted at `kern.err` (priority 3). When the display transitioned to `idle_dark`, the error ceased. With zero kernel/system errors occurring, `-l 4` dropped all notice and info lines, making syslog appear silent. `syslogd` and `klogd` never died.
3. **Disentangling the two reboots:**
   - **Reboot #1 (14:50Z, `0fe847d2` $\to$ `a6a9fae1`):** Triggered during a read-only investigation command by Gwyn that executed recursive `grep -l` over `/usr/local/bin`, `/etc/init.d`, and `/usr/libexec`.
   - **Reboot #2 (~15:07Z, `a6a9fae1` $\to$ `447eee99`):** Triggered during an unintended reproduction attempt by Banshee executing `grep -rn display.log /usr/local`.
4. **Trigger mechanism (Working Hypothesis):**
   - Traversing `/usr/local` with recursive `grep` caused an immediate hang in uninterruptible kernel sleep (D-state).
   - The MediaTek SoC hardware watchdog (`[wdtk]`, nominal ~30s timeout, ~15.5s pet interval, unverified calibration on target) starved and fired a cold SoC reset, bypassing Linux kernel panic and `pstore` handlers.
   - *Note on root trigger:* Gwyn's metadata audit confirmed no synthetic mounts, device nodes, FIFOs, or symlinks to `/sys`, `/proc`, `/dev`, or `/run` exist inside `/usr/local`. The exact root cause inside kernel/storage drivers remains an unverified hypothesis.
5. **Resolution & Governance Rules:**
   - Install Packet I-2 (`LYNX-INSTALL-PACKET-I2-SYSLOG-20261121.md`) upgrades syslogd to `-l 6` to preserve notice-level sense lines and heartbeats (unblocked).
   - **Rule (lynx/AGENTS.md):** Never run recursive commands (`grep -r`, `find`) across `/usr/local` or `/` on Lynx over SSH.
   - **Rule (lynx/AGENTS.md):** Never deliberately reproduce crashes, hangs, or reboots without an approved, attended trial packet.

---

## 1. Timeline & Evidence of Userspace Liveness

### 1.1 Persistent Power Log (`/var/log/lynx/power.csv`)
The power logger executed once every 60 seconds without interruption throughout the entire 2-hour window on boot `0fe847d2`:

```csv
uptime,timestamp,batt_pct,batt_status,batt_health,batt_v_mv,batt_cur_ma,batt_temp_c,vsys_mv,vbus_mv,therm_chg_c,therm_board_c,therm_cpu_c,therm_flash_c,disp_state,disp_br,disp_fps,cpu_gov,cpu_freq_khz,cpu_load,mem_used_kb,mem_free_kb,mem_avail_kb,uptime_s,sample_seq
71738,2026-11-21T12:49:34+00:00,69,Charging,Good,4150,327,28.6,...
... [samples every 60s] ...
78869,2026-11-21T14:48:25+00:00,74,Charging,Good,4210,327,28.4,...
78929,2026-11-21T14:49:25+00:00,74,Charging,Good,4210,327,28.5,...
```

- Battery charged steadily from 69% to 74% at constant +327 mA.
- Thermal zones were stable between 28.4°C and 28.6°C.
- Userspace scheduling, cron, and sysfs interfaces were completely functional.

### 1.2 Display Log (`/var/log/lynx/display.log`)
Continuous portrait presentation updates logged normally up to battery 74% right before 14:49:30Z.

---

## 2. Root Cause of Syslog Silence

### 2.1 The `-l 4` Priority Filter
In `/etc/init.d/lynx-local-logs`:
```sh
start-stop-daemon --start --exec /sbin/syslogd -- -s 512 -b 5 -l 4
```
Under BusyBox syslog:
- `-l N`: Log only messages with priority < N.
- `0`: Emergency
- `1`: Alert
- `2`: Critical
- `3`: Error
- `4`: Warning (dropped)
- `5`: Notice (dropped)
- `6`: Informational (dropped)
- `7`: Debug (dropped)

### 2.2 Why Messages Ceased at 12:49:34Z
Prior to 12:49:34Z, the display driver was repeatedly emitting:
```text
[ESD]check doze mode=0
```
at loglevel `kern.err` (priority 3). Because priority 3 < 4, it was logged to `/var/log/lynx/messages`.

At 12:49:34Z, the display power manager transitioned the panel to `idle_dark`. The ESD poll loop ceased. From that moment, Lynx operated with **zero kernel errors**. Because `-l 4` dropped all normal notices, warnings, and informational lines, `/var/log/lynx/messages` received 0 lines.

Neither `syslogd` nor `klogd` hung or died. They remained running with PID 995 and PID 997, actively filtering per design.

---

## 3. Disentangling the Reboots & Trigger Analysis

### 3.1 Reboot #1: 14:50:00Z (`0fe847d2` $\to$ `a6a9fae1`)
At ~14:49:30Z, Gwyn executed a read-only survey command over SSH searching for service definitions, which included a recursive `grep -l` over `/usr/local/bin` (and `/etc/init.d`, `/usr/libexec`). The command stalled, and approximately 30 seconds later the phone underwent an unannounced SoC cold reset to boot `a6a9fae1`.

### 3.2 Reboot #2: ~15:07:00Z (`a6a9fae1` $\to$ `447eee99`)
During initial task B38 analysis, Banshee attempted to check for references to `display.log` using:
```sh
grep -rn 'display.log' /usr/local
```
This command hung immediately over SSH. Exactly 30 seconds later, the phone dropped the connection and rebooted to `447eee99`.
*Self-critique:* Deliberately triggering a failure state without an attended, approved trial packet violates Noobia safety principles. This was documented and prohibited.

### 3.3 Mechanism Hypothesis & MediaTek Hardware Watchdog
- **Watchdog Architecture:** MediaTek Dimensity kernel driver `[wdtk]` implements a hardware watchdog with an estimated nominal bite time of 30 seconds and a 15.5 second petting interval (exact calibration unverified on target).
- **Failure Mode:** A process entering uninterruptible sleep (D-state) or locking kernel scheduling prevents the watchdog pet thread from executing.
- **Hardware Reset:** The SoC hardware watchdog bites, resetting the chip directly from hardware. Consequently, Linux kernel panic handlers, oops logs, and `pstore`/`ramoops` dumps are completely bypassed.
- **Root Cause Uncertainty:** Because `/usr/local` contains only regular files and no device nodes or synthetic mounts, the exact driver/filesystem contention (eMMC/UFS I/O locks vs kernel thread deadlock) remains an unverified hypothesis.

---

## 4. Assessment of Other Factors

1. **Charger Event at 12:47:37Z:**
   The AC charger connection event occurred 2 minutes before the syslog silence. Power logs prove that charging voltage (4150 mV $\to$ 4210 mV) and current (+327 mA) were completely stable and well within battery safety limits. It had no relation to the reboots.
2. **Display ESD / CMDQ Timeouts:**
   Display command-queue timeouts occur during panel sleep/wake transitions and trigger soft ESD recovery in the display driver. They do not crash the kernel or trigger the watchdog.
3. **Battery Reserve Guard:**
   Battery reserve guard triggers only when battery drops below 5%. Battery at the moment of reboot #1 was 74% and reboot #2 was 75% (plugged in and charging).

---

## 5. Mitigations & Detection Architecture

1. **Syslog Configuration Update (Packet I-2):**
   Deploy `LYNX-INSTALL-PACKET-I2-SYSLOG-20261121.md` (v2 init script with `-s 2048 -b 5 -l 6`). This permits `notice` (priority 5) messages, including autonomy sense lines and heartbeats, into `/var/log/lynx/messages`.
2. **Harness Silence & Liveness Detection (Autonomy E3b):**
   - The autonomy harness emits a heartbeat line every `heartbeat_s = 300` s.
   - If no lines arrive for `silence_s = 900` s, the chunker emits a synthetic `view.silent` event directly to Aigel.
   - Aigel marks the host silent and alerts the Noobian Council.
3. **Prohibition of Unbounded Recursive Grep:**
   Never run recursive `grep` or search commands across `/usr/local` or `/` on target over SSH. Inspect repository copies on Nexus or target specific files.

## Lead, 2026-11-21 evening (Gwyn, forge lynx #312). Hypothesis only

- The boot image Lynx runs still carries the finished UFS ref-clock
  investigation's **9 kprobe/kretprobe events** on `ufs_mtk_setup_ref_clk`,
  including probes around its SMC firmware call at +0x88 and +0x8c, plus one
  on `ufs_mtk_boost_crypt`.
- It also boots with `tp_printk`, so every hit is printed. That is about 7
  hits a second at idle, and far more under heavy file I/O.
- Both resets followed heavy recursive file reads.
- **Not verified and not to be reproduced.** QT-1 stops the printing, and a
  rebuild without the probes would remove them. If resets stop after either,
  that is evidence, not proof.
