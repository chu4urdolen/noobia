# Lynx V46 Alpine self-maintenance

V46 remains the exact working `boot_a` image, SHA-256
`6c487df1c16af1717e045167c165271065e9060c5a02b16b8e1b3ce3eca28f91`.
All changes below were made through Alpine-owned pinned SSH on port 2222 to
the persistent ext4 root. No boot image, bootloader, recovery or slot B
partition was changed. Rescue SSH on port 22 remains separate.

## Battery and thermal safety

The V46 image still starts the original battery temperature watcher (45°C
power-off), CPU/SoC watcher (60°C power-off), three CPU cooling controls and
health supervisor. The health supervisor checks fresh gauge data, sensor and
watcher presence every five seconds; three consecutive failures request
power-off. The existing charger guard requests power-off if a supply reports
online. During the current Nexus USB connection, that supply flag read zero
while the identified battery gauge reported positive current and increasing
capacity. This is evidence of charging, but the phone's charging protections
and behavior across reboot remain unverified; see
`V46-CHARGING-RESERVE-STAGE.md` for the controlled trial and rollback state,
and `V46-CHARGER-READONLY-AUDIT.md` for the live charger device-tree evidence.

The new persistent `lynx-battery-reserve` OpenRC service reads the same
identified ZY0603-family gauge every 30 seconds and requests orderly power-off
after three consecutive valid readings at or below 20% charge, or three
consecutive gauge read errors. A forced BusyBox power-off is a 15-second
fallback. It does not write charging controls or gauge registers. The
guard's local normal, boundary, repeated-low and repeated-error fixtures
passed; the exact script and OpenRC service were installed and independently
verified on boot ID `135b8a44-fc09-427c-9b5f-53ac4add7527` at 88% charge:

- `logs/v46-battery-reserve-install-1792699349648809360/result.json`
- `logs/v46-battery-reserve-verify-1792699382654750044/result.json`

## Local persistent diagnostics

`lynx-local-logs` starts BusyBox syslogd and klogd with no remote forwarding.
Its log directory is private (`0700`) on Alpine's ext4 root. The main log
rotates at 512 KiB with five retained rotations and keeps notice-or-higher
severity. It also copies up to 256 KiB of the early `/run/lynx/boot.log`
into a boot-ID-named file when present and keeps a bounded 512 KiB kernel
snapshot for the current and previous boot. An independent live test injected one service-log marker and one
kernel-log marker and found both in the persistent log:

- `logs/v46-local-logs-install-1792699512858625927/result.json`
- `logs/v46-local-logs-verify-1792699538995594227/result.json`

The first reboot showed that the original 256 KiB/three-rotation logger was
too small: kernel boot chatter displaced the old marker even though Alpine
and all six services started. The revised policy above is being installed
and retested. The prior V46 persistent stage log remains separate and
unchanged.

On the first new boot, ID `755b6746-be00-4838-b580-955217f86ab7`, exact V46
and native Alpine SSH passed:
`logs/v46-autonomous-alpine-verification-1792700228251085169/result.json` and
`logs/v46-alpine-native-ssh-1792700233601560788/result.json`. The
cross-boot marker verifier correctly failed while all six service statuses
passed: `logs/v46-maintenance-reboot-1792700233601373836/result.json`.
The `/var/log/lynx/messages*` rotation set had filled during boot, so the
old marker was gone. The revised logger was installed with a RAM backup of
the old service, restarted, and independently proved with new service and
kernel markers:
`logs/v46-local-logs-update-1792700314118046562/result.json`,
`logs/v46-local-logs-verify-1792700318466743032/result.json`.
Persistence of these new markers still needs a second reboot.

On boot `f6230cac-8d41-48da-bf28-2700e9ff56f1`, the UFS driver produced
enough warning-level kernel messages to fill the log rotation rapidly. The
logger service was updated to keep errors and higher (`syslogd -l 4`) while
retaining the bounded boot-ID kernel snapshot and a persistent copy of its
previous notice-level service under `/root/lynx-rescue/`. The live update,
error-kept/warning-filtered test, maintenance check, and rescue SSH hash
audit passed:

- `logs/v46-local-logs-update-1792783739468265457/result.json`
- `logs/v46-local-logs-verify-1792783769273400266/result.json`
- `logs/v46-maintenance-verify-1792783792264268924/result.json`
- `logs/v46-live-recovery-audit-1792783818778351879/result.json`

The updated logger survived the later controlled V47 reboot: a previous
error marker and previous boot log remained accessible on the new Alpine
boot (`logs/v47-live-verify-1792785655574139377/result.json`). Its severity
filter applies to the main syslog, while boot diagnostics and kernel
snapshots remain available separately.

## Clock and debug tools

The battery-backed real-time clock is not exposed in this V46 userspace.
The phone's wall clock read January 1970 during this boot, which caused
Alpine's HTTPS package fetch to reject server certificates. Nexus's clock
was confirmed NTP synchronized, then used once to seed Lynx's UTC clock:
`logs/v46-clock-seed-1792784029661535867/result.json`. The initial package
attempt failed without installing packages, and a retry installed and
verified `strace`, `lsof`, and `iw` from Alpine's signed repositories:
`logs/v46-debug-basics-1792783997441172433/result.json`,
`logs/v46-debug-basics-1792784030142214661/result.json`.

Chrony and its OpenRC package were installed. Alpine's packaged `chronyd`
service needs the generic `net` service, whose `networking` startup fails
on Lynx. Its runlevel link was removed and its configuration restored after
this failed start:
`logs/v46-chrony-dependency-revert-1792784113374217842/result.json`.
The local `lynx-time-sync` service instead depends on the working
`lynx-wifi` service and runs Chrony in the background without delaying
OpenRC for NTP convergence. V46 creates `/dev/null`, `/dev/random`, and
`/dev/urandom` with mode 0660, so the local service restores their normal
0666 permissions before starting. A saved `strace` showed that the initial
mode blocked `chronyc` from opening `/dev/urandom`:
`logs/v46-chronyc-strace-1792784155327833374.txt`.
The local service is now active, and Chrony reported `Leap status: Normal`
with reachable NTP sources. Its exact service hash, runlevel link, device
permissions, SSH, safety services, and synchronized status passed a read-only
verification:
`logs/v46-time-sync-verify-1792784236723022921/result.json`.

The clock still starts unset until Wi-Fi and this service run. The later
controlled V47 reboot verified Chrony `Leap status: Normal` on the new
Alpine boot (`logs/v47-live-verify-1792785655574139377/result.json`). To
disable it through Alpine SSH,
run `rc-update del lynx-time-sync default` and
`rc-service lynx-time-sync stop`; the original V46 boot image is unaffected.

## Bounded power history

The separate `lynx-power-history` OpenRC service samples the identified
ZY0603 gauge once per minute. It writes boot ID, monotonic uptime, UTC epoch,
capacity, signed pack current, battery temperature, and pack voltage to
`/var/log/lynx/power.csv`. It rejects invalid gauge identity, error flags,
and out-of-range values. The private CSV uses mode 0600 and rotates at
256 KiB with three retained files. It reads sensors and writes logs only;
the health and reserve services retain all shutdown authority.

The exact scripts were installed on the current V46 boot after pinned SSH,
OpenRC, healthy gauge, service and storage checks. The first sample, OpenRC
start, file permissions, and safety-service status passed:
`logs/v46-power-history-install-1792784859755324402/result.json`.
After the next minute, a read-only check verified a distinct later sample
and both safety services still running:
`logs/v46-power-history-verify-1792784927871853849/result.json`.
The later V47 reboot retained rows from the previous V46 boot and wrote
new-boot rows while the service was running:
`logs/v47-live-verify-1792785655574139377/result.json`.
To disable future starts, run `rc-update del lynx-power-history default`
through Alpine SSH; the service files and CSV remain for inspection.

## Automatic service recovery

`lynx-maintenance` is itself run by OpenRC
[`supervise-daemon`](https://github.com/OpenRC/openrc/blob/master/supervise-daemon-guide.md)
with bounded
respawn settings. Every 30 seconds its script checks the health and battery
reserve services, repairs failed local logging with an OpenRC restart, and
restarts only a demonstrably dead Alpine Dropbear worker when WLAN and keys
are present. It never stops rescue SSH, loads a kernel module, alters thermal
or charging settings, or flashes a partition. Two consecutive unavailable
safety checks request power-off. Wi-Fi loss is recorded without attempting
an unreviewed network reset.

The installed same-boot check passed:
`logs/v46-maintenance-install-1792699658656796203/result.json` and
`logs/v46-maintenance-verify-1792699704715843842/result.json`.
One supervised fault trial stopped only Alpine Dropbear's parent process
through rescue SSH; the watcher restored port 2222 within two five-second
probes, and a new full maintenance verification passed:
`logs/v46-ssh-recovery-1792699806252902087/result.json`.
One supervised syslogd fault trial restored both local logging workers by
the fifth five-second probe. A fresh service and kernel marker test then
passed: `logs/v46-local-logs-recovery-1792699848333754626/result.json`,
`logs/v46-local-logs-verify-1792699878989501691/result.json`.
These trials prove recovery for the two induced faults on this boot; they do
not prove Wi-Fi outage recovery or every possible service failure.

After the first reboot, the maintenance service's OpenRC dependencies were
changed so only the foundational health service is required; reserve,
logging, Wi-Fi and Alpine SSH are ordered before it when available. This
lets the watcher start and handle a failed optional service instead of being
held back by that failed dependency. The running watcher was not restarted;
the revised service file was hash-checked and installed for the next boot:
`logs/v46-maintenance-dependencies-1792700350722533626/result.json`.
Same-boot verification passed afterward:
`logs/v46-maintenance-verify-1792700355226832353/result.json`.

## Rollback

The original V46 image remains intact, and the exact V33 fallback image is
still SHA-256
`1d65456979d8a48d31de77c987b8aaf9b5ac11af62c51d00fdaff68ad47e747f`.
Before touching a runlevel link, `tools/rollback_v46_maintenance.py` checks
the pinned rescue SSH connection, exact V46 `/init` hash, kernel release,
OpenRC root path, and all three new service links. The read-only preparation
passed on the current boot:
`logs/v46-maintenance-rollback-1792699945433543490/result.json`.
Its separate `--apply --prepared <receipt>` action moves only the three
new default-runlevel links into a private directory on Alpine ext4. It does
not remove service files, stop current processes or change `boot_a`; a
subsequent orderly reboot completes the userland rollback. This action has
not been invoked. If Alpine SSH is unavailable, the same tool can run
through pinned rescue SSH on port 22 while the persistent root is mounted.

The guarded Fastboot V33 `boot_a` restoration procedure remains a last
resort, subject to exact identity and image-hash checks. Do not choose the
recovery menu's Format data action.

## Current boot test

An orderly OpenRC reboot was issued from the verified V46 session after all
new services and the rollback preflight passed:
`logs/v46-openrc-reboot-1792699972483211836/result.json`.
The new-boot collector is
`logs/v46-health-window-1792699975312321972/result.json`. It saw boot ID
`755b6746-be00-4838-b580-955217f86ab7`, exact V46, Alpine/OpenRC PID 1,
and native SSH. The installed logger and maintenance dependency changes were
verified on that boot. The logger's revised rotation policy had not yet been
tested across a reboot.

On 2026-10-23, a full power-off cold start reached exact V46 BusyBox and then
Alpine/OpenRC PID 1 on boot ID `04f4bc3e-0362-48a2-98a5-df46a3c6af8a`.
The first health reading was 20% battery at 21.9°C. Its pinned address was
`192.168.100.8`; the former `192.168.100.6` address was a different SSH host
and must not be treated as Lynx. The cold-boot collector and exact V46 proof
are `logs/v46-health-window-1792765671349267490/result.json` and
`logs/v46-autonomous-alpine-verification-1792765848234241197/result.json`.

Before the reserve guard shut this new boot down, a read-only pinned Alpine
SSH transfer captured the private `/var/log/lynx` directory at
`logs/v46-persistent-logs-1792765851060578998/lynx-logs.tar`, with SHA-256
`5c724f22054ad151620947712da70c3ecf1c1821e780e5da18814c110b4cf659`.
The retained messages include
`LYNX_BATTERY_RESERVE_SHUTDOWN reason=low_capacity` at kernel uptime
`60368.535740` seconds from the previous boot. This confirms an orderly
reserve shutdown, not a kernel crash. The revised rotating syslog did not
retain the earlier test marker after roughly 17 hours of kernel chatter;
important event retention needs improvement. The boot-ID-named early boot
logs for previous boots did survive. At this historical point charging had
not yet been observed to raise capacity. A later Nexus-connected V46 session
recorded positive gauge current and rising capacity, as described above.

The subsequent offline source change limited persistent syslog to
error-or-higher severity.
The retained archive showed almost all rotation space consumed by repeated
`kern.warn` UFS clock messages (the most recent rotation had 2,508 warnings
and 134 errors). The logger proof was adjusted to inject an error-level
service and kernel marker. This policy was initially staged only; it was
later installed and verified on the live boot, with the previous service
copied to persistent rescue storage. The receipts are listed above.
`tools/update_v46_local_logs.py` now accepts the prior successful update
receipt and a new same-boot V46 verification. Its preflight refuses an
update below 40% battery or with any power supply reporting online. The
staged policy can be installed only after charging is demonstrated.
The staged service also records the boot ID beside its kernel snapshot so a
same-boot logger restart refreshes the current snapshot without replacing
the previous boot's snapshot.

## Charging gate after reserve shutdown

The matching stock kernel config has
`CONFIG_MTK_KERNEL_POWER_OFF_CHARGING=y`; its Kconfig explains that the
kernel and a userspace KPOC service cooperate to charge while powered off.
This does **not** establish that our custom initramfs provides that service
or that the unloaded OPLUS/Type-C modules can charge the battery. First use
a short, observed wall-charger trial while Lynx is off; note any charging
icon, Orange State boot, reboot loop, or heat, and stop on the latter two.
Do not resume prolonged Linux boots or flash experiments at 20% charge.

The first charging attempt used a Nexus USB port. The user saw Orange State
then a dark display. Nexus `lsusb` showed no Lynx USB device, and pinned Wi-Fi
SSH did not answer; these observations cannot establish whether 5 V power is
reaching the battery. No phone-side gauge measurement was possible. Use the
original OnePlus wall charger and cable for the next short observed check,
then verify a rising battery gauge before resuming Linux development.

Later in the same Nexus-cable trial, pinned SSH found a **new** V46 BusyBox
boot, ID `d004a4e8-34d5-4839-83e8-15756d2498b9`, at `192.168.100.8`.
Thus the dark display was not proof of power-off. The early charger supply
reported `online=0`, `Not charging`, but once the custom read-only ZY0603
gauge initialized it measured +145 mA; three subsequent samples 10 seconds
apart measured +132, +127, +134 mA at 20% and 24.6–24.7°C, with pack voltage
7494, 7494, 7495 mV. The matching gauge documentation defines negative
current as discharge, so these positive readings support modest charging
**while Linux was running** despite the incomplete charger-supply driver.
SSH disconnected at 20% around the reserve guard's expected shutdown time;
this run has not yet yielded a persistent log proving the exact disconnect
cause, and capacity had not risen.
Neither continued charging while off nor safe long-term charging is verified.
The private read-only receipts are
`logs/v46-charging-ssh-watch-1792766705031320971/result.json` and
`logs/v46-battery-trend-1792766917990572793/result.json`.
