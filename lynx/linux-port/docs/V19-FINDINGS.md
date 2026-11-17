# V19 architecture and findings

## What works

The CPH2493/MT6983 boots our BusyBox PID1 on the matching OEM kernel
`5.10.149-android12-9-o-g311738fbb5a8`. Stock-compatible modules initialize the
storage and WLAN path. wlan0 associates with Noobia using WPA2-PSK, obtains a
DHCP lease, and accepts pinned key-only Dropbear SSH.

Hardware proof includes host-key verification, exact kernel release, PID1
`/bin/busybox`, init/BusyBox SHA256, current boot token and UID0. A second live
status read showed `wpa_state=COMPLETED`,192.168.100.9/24 and a default route
through192.168.100.1. The Orange State warning was not bypassed. No display
initialization or full postmarketOS installation is claimed.

## Boot arrangement

boot_a contains the stock kernel and a small legacy-LZ4 primary initramfs. A
larger gzip supplemental cpio sits at byte25165824 inside the64MiB boot image.
The primary stage loads the validated storage dependencies, identifies its own
boot partition, opens it read-only, reads a bounded supplemental archive and
verifies its SHA256 before extracting it into RAM. This fits the original
boot metadata coverage limit21889024 while retaining the stock metadata/footer.

Modified boot contents do not match the OEM payload hash. This works with the
already-unlocked bootloader and matching boot foundations; it is not an OEM
signed image and must not be relocked. The proven kernel hash is
`cbc9f5dc54b5198ddd1e82d5d7bde96f43cbb383a663726ddd68919b0639d3af`.

The kernel has no devtmpfs. Init mounts proc/sysfs and tmpfs/dev, creates the
essential console/null nodes, then runs mdev. A continuing mdev netlink daemon
is necessary for firmware requests that arrive after the initial device scan.
Runtime rootfs, logs and configuration changes use RAM. Factory calibration
is read from matching stock data and submitted to the driver in RAM.

## Dependencies and traps that mattered

- Preserve stock directory/symlink relationships. `/vendor/firmware` must stay
  a directory; mirror matching firmware there. Stock `/odm/etc` resolves into
  `/vendor/odm/etc`, so supplemental configuration belongs at that target.
- The matching UFS clock-provider sequence and guarded MT6685/clkbuf bindings
  precede storage/radio use. A bound module alone does not prove a working bus.
- The standard station command can time out while an asynchronous driver
  worker is still progressing. The guarded continuation requires current-token
  probe-success evidence, a stable idle worker stack, and matching netdev/module
  identity before one additional normal station request. It never overlaps
  requests or forces registers, probe state or calibration writes.
- The kernel has firmware user-helper fallback enabled but no executable
  uevent helper. `mdev -s` alone cannot serve later firmware requests.
  `mdev -df -vv` listens on the normal kernel netlink channel. Actual logs
  now show missing optional firmware candidates being completed promptly.
- **This wpa_supplicant2.11 build does not support `-f`.** That argument prints
  usage and exits0 without starting a daemon. This caused earlier startup
  checks to falsely pass. The exact ARM binaries reproduced it locally.
  V19 uses an owned foreground child, shell log redirection, PID tracking and
  a real bounded `PONG` before association polling.

## Observability

Before SSH, software reset timing encoded bounded diagnostic categories.
Calibration, non-interference, reset evidence and non-overlapping slots were
required; the timing result was never a complete kernel console. Read-only
`/proc/PID/stack` narrowed the failed startup to connectivity and firmware
loading. initcall_debug and RAM stage journals preserved context.

With SSH, full dmesg and checksummed stage journals can be copied directly.
The first successful collection decoded2supervisor,84bootstrap and105Wi-Fi
records. A compact archive of44runtime records validated successfully, plus
827344bytes of kernel log. Capturing all of /run/lynx included bulky image
payloads and hit a35s deadline; the collector now omits those while preserving
runtime records. Raw and failed attempts remain local for offline analysis.

## Timings and repeatability

The successful phone log records WPA start85.14s, association wait86.14s,
DHCP87.15s and SSH-ready91.13s. Host discovery and pinned proof arrived around
109s after collector startup. Launching the collector and trial together avoids
approval delays consuming the observation window. Independent local tests run
in parallel when they have no shared mutation or hardware access.

The reconstruction recipe produced a byte-identical64MiB V19 image from the
private content-addressed cache and stock boot alone. Earlier experimental
images are no longer required to reproduce the working artifact.

## Next work

Keep V19 unchanged as the fallback baseline. First inspect live storage layout,
filesystem support, battery/charger status and reset/watchdog behavior through
SSH. Persistent rootfs/logging and power management need a design based on
those observations. No new partition write or broad firmware replacement is
needed simply to investigate them.
