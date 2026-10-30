# Lynx shared radio calibration boundary

## V50 failure

On 2026-10-29, the exact stock Bluetooth and GNSS modules loaded on V50 in
RAM without disrupting Alpine or Wi-Fi. Bluetooth created `/dev/stpbt` but no
HCI controller; the stock BTIF build sets `USE_DEVICE_NODE=1`, so Linux HCI
registration is skipped by design. GNSS created `/dev/gpsdl0` and
`/dev/gpsdl1`. These device nodes disappear on reboot because the modules
were not added to V50's boot sequence.

Opening `/dev/gpsdl0` on the running V50 boot waited about 25 seconds, then
returned without measurements. Opening `/dev/stpbt` with the exact stock
firmware files staged in RAM stayed blocked in kernel state D. The timed
userspace probe could not terminate that `open()` call. The stack was:

```text
conninfra_core_pre_cal_blocking
conninfra_pwr_on
btmtk_set_power_on
btmtk_btif_open
bt_open
BT_open
```

The kernel repeatedly logged `pre_cal status=[0]`. The matching stock
`conninfra.cfg` contains `pre_cal_mode=3`, and the fresh boot confirmed that
the kernel loaded that value. Source review shows that calibration is
scheduled when both Bluetooth and Wi-Fi drivers are registered and both
radios are still powered off. V50 powers Wi-Fi before registering Bluetooth,
leaving the status at zero when either BT or GNSS requests shared radio
power. V52's successful calibration and Bluetooth trial later confirmed this
as the cause of the Bluetooth stall. It was also a contributor to the V50 GNSS
stall; the receiver has further work beyond calibration.

The Bluetooth probe restored the original firmware path and canceled its
reboot watchdog after a healthy SSH check. The still-blocked kernel process
was later cleared by a normal Linux reboot. Lynx returned to V50 Alpine with
a new boot ID and clean health checks. Evidence:

- `logs/v50-gnss-open-1793306208339440038/result.json`
- `logs/v50-bluetooth-open-1793306335652884321/result.json`
- `logs/v50-bt-gnss-precal-stall-1793347175612979840/`
- Source checkout: `sources/oneplus-mt6983-modules/vendor/mediatek/kernel_modules/connectivity/conninfra/core/conninfra_core.c`
- BT device-node build: `sources/oneplus-mt6983-modules/vendor/mediatek/kernel_modules/connectivity/bt/mt66xx/btif/Makefile`

## V52 image and restoration

The **V52 image** preserves the exact V50 kernel, `/init`, and
stock `conninfra.cfg`. It adds the two matching stock Bluetooth modules and
`BT_FW.cfg` to the rescue supplement. Its radio load list places
`btif_drv.ko` and `bt_drv_6983.ko` immediately after the Wi-Fi driver module,
before the V50 Wi-Fi station power-on command. This lets the stock shared
calibration run while both radios are off. It does not add Bluetooth to Alpine
startup or attempt pairing. GNSS still needs a native receiver userspace path.

Builder: `tools/build_v52_bt_before_wifi.py`. Exact candidate:
`linux-port/artifacts/bt-before-wifi-v52-offline/nord3-bt-before-wifi-v52-untested.img`,
SHA-256 `9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf`.
The builder verified payload checksums, matching module hashes, the new load
order, unchanged kernel and rescue `/init`, a round-trip parse, and an
unchanged image tail. On 2026-10-30, Fastboot wrote this exact image to
`boot_a` only and reported a complete send and write. The live boot hash
matched `9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf`.
The bootloader, slot B, and recovery-related partitions were untouched.
Flash receipt: `logs/v52-boot-a-trial-1793352654398289025/result.json`;
reboot receipt: `logs/v52-boot-a-trial-1793352671480123173/result.json`.

The guarded Fastboot script `tools/lynx_boot_a_v52_trial.py` has an offline
`--prepare` mode and only touches `boot_a` for a live trial. It checks the
exact V52 candidate and V50 rollback image before any Fastboot command.
The exact rollback is `--restore-v50` with V50 SHA-256
`6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59`.
The flash followed a fresh V50 health reading at 49%, with positive charge
and normal temperatures. Preserve the working V50 image and Fastboot access.
If a future V52 boot fails, restore V50 to `boot_a` and stop for diagnosis.

V52 reached rescue SSH, Wi-Fi, and Alpine. The kernel recorded the expected
calibration scheduling from status 0, Bluetooth calibration success, Wi-Fi
calibration success, and final `pre_cal` return 0. All eight core Alpine
services passed health checks, and the battery reached 50% while charging.
Full early boot evidence: `logs/v52-precal-1793352878714805705/`.

A first valid GNSS position must be checked outdoors against an independent
position and time; no position has yet been measured on Lynx. For Bluetooth,
the stock driver needs a persistent native `/dev/stpbt` bridge or a separately
validated BlueZ-oriented rebuild before Noobian protocol traffic.

## Prepared native Bluetooth transport probe

`tools/lynx_bluetooth_hci_probe.py` sends complete H4 HCI packets through the
stock `/dev/stpbt` character interface. Its first commands are Reset and Read
BD Address. An optional, bounded LE advertisement names the device `Lynx` so
Nexus can attempt discovery without pairing. This is a transport probe, not a
Noobian protocol bridge. The H4 framing and 15-byte LE advertising parameter
layout have local unit tests.

`tools/trial_v52_bluetooth_hci.py` stages that probe and the matching firmware
in RAM over pinned SSH. It verifies the exact V52 boot hash, current Alpine
health, and charge before opening the radio. A separate 90-second reboot
watchdog remains armed if the open or HCI exchange stalls; it is canceled only
after a successful exchange, restored firmware path, and healthy Alpine check.
On V52, `/dev/stpbt` opened in about 0.55 seconds and answered HCI Reset and
Read BD Address. A second guarded trial advertised `Lynx` for 18 seconds;
Nexus discovered address `00:00:46:67:61:01` under that name at about -44 dBm.
The address matched the HCI response. The firmware path was restored, the
watchdog was canceled, and Alpine stayed healthy. No pairing or Noobian
Bluetooth traffic has been tested. Receipts:
`logs/v52-bluetooth-hci-1793352918277135581/` and
`logs/v52-bluetooth-hci-1793353005396840284/`.

The V52 kernel has built-in Bluetooth, LE, RFCOMM, and H4 support, but
`CONFIG_BT_HCIVHCI` is disabled and the stock BTIF module was built for the
character-device path. A later bounded PTY bridge to the built-in `N_HCI`
line discipline made that stock path visible to BlueZ; see the later trial
below.

## GNSS userspace boundary

The matching stock package contains Android `mnld`, but its interpreter is
`/system/bin/linker64` and it depends on Android libraries and services.
Alpine cannot run that binary directly. The matching Linux kernel modules
create transport nodes, not position measurements. Shared calibration must
work first, followed by a native GNSS firmware/protocol implementation or a
carefully isolated compatibility layer. Do not report the node's presence as
a position fix.

`tools/trial_v52_gnss_link.py` is prepared for the next step. It requires a
successful Bluetooth HCI receipt from the **same V52 boot**, verifies the
matching stock GNSS data-link module, stages it in RAM, and opens `/dev/gpsdl0`
under a reboot watchdog. It does not claim a position.
An initial preflight with four GNSS modules stopped before loading anything
because V52 had not loaded the optional SCP dependencies. The data-link
module declares only `conninfra` as its direct dependency, so the next test
loaded that single module. The kernel recorded `OPENING -> OPENED` and GPS
power-on on 2026-10-30. A subsequent read waited until its 20-second timeout;
the kernel then closed the link and powered GPS off. Alpine remained healthy,
and the watchdog was canceled after verifying no probe process remained. The
trial tool now stops after open and close so it cannot repeat that blocking
read. Source review explains the behavior: `gps_each_device_read()` calls
`gps_each_link_read()`, which requests `GPS_DL_RW_NO_TIMEOUT` and does not
honor the file's `O_NONBLOCK` flag. Evidence:
`logs/v52-gnss-link-1793353116845876827/` and
`sources/oneplus-mt6983-modules/vendor/mediatek/kernel_modules/connectivity/gps/data_link/gps_each_link.c`.
No GNSS position has been measured.

### Stock GNSS userspace audit, 2026-10-30

The exact August CPH2493 OTA contains `mnld`, `gps.default.so`, and their
Android libraries. `tools/extract_august_system_gnss_reference.py` recovered
the matching system image; `tools/prepare_august_gnss_bundle.py` assembled a
17.7 MB bundle with all 28 direct and transitive ELF dependencies. On V52,
the stock Bionic linker resolved both binaries from a RAM staging directory.
This is a loader check, not a receiver check. Evidence:
`logs/v52-gnss-bionic-linker-1793353979079849355/`.

`tools/lynx_gnss_props.c` supplies only the observed MT6983 and ADIE property
values for a short audit. `tools/lynx_gnss_sandbox_runner.py` starts `mnld`
inside a private mount and network namespace and a RAM chroot without device
nodes or persistent storage. The daemon remained alive for the full eight
seconds and requested the expected chip, ADIE, and driver-ready properties;
the runner then killed it. No GPS hardware node was exposed, and the sandbox
was removed. Evidence: `logs/v52-gnss-sandbox-1793365530010193971/`.
The stock package uses an AIDL `IGnss/default` service. Its older
`gps.default.so` lacks the legacy `HAL_MODULE_INFO_SYM`, so the BF7 legacy HAL
example is not directly applicable. `tools/extract_august_system_ext_gnss_reference.py`
recovered the exact `system_ext` image; the missing AIDL library was found in
its VNDK v31 APEX. `tools/inventory_august_gnss_service.py` now reports a
closed 26-ELF dependency set. This maps the Android path but does not require
running Binder on Alpine.

### Native NMEA milestone, 2026-10-30

`mnld`'s syscall trace showed it needed `/dev/gps_emi`, `/dev/gps_pwr`, and
`/dev/gps2scp`. `tools/trial_v52_gps_pwr.py` loaded the exact power module in
RAM. `tools/trial_v52_gps_scp_stack.py` then loaded the eight matching SCP
dependencies in order, checking Alpine and Wi-Fi after each. All completed and
the GPS-to-SCP node appeared. No boot or data partition was written, and the
watchdogs were canceled. Receipts: `logs/v52-gps-pwr-1793366856224152193/`
and `logs/v52-gps-scp-stack-1793367018203765609/`.

`tools/trial_v52_gnss_mnld.py` runs the exact stock `mnld` and Bionic
libraries in a RAM chroot with a private mount and network namespace. Only the
verified GPS device nodes and a RAM copy of the 54-byte factory calibration
are exposed. `tools/lynx_mnl_listener.py` binds the stock abstract
`mtk_mnl2hal` socket. The matching `gps.default.so` disassembly confirms the
little-endian start packet `(1, 102, 1.4)` and stop packet `(1, 103)` sent to
`mtk_hal2mnl`; the listener uses those exact packets in a 20-second trial.
`libcustom_nvram.so` and `/dev/gpsdl1` were needed for receiver initialization.
The stock daemon then opened both GPS data links and emitted NMEA sentences.
The GPS hardware powered off after the bounded trial, and Alpine stayed
healthy. Evidence: `logs/v52-gnss-mnld-1793367608289346792/`.

`tools/parse_lynx_mnl_nmea.py` verified 109 NMEA checksums. The last GGA
reported fix quality **0** and **0 satellites in use**; RMC status was **V**
(invalid). Some GGA coordinate fields were populated despite the invalid fix,
so the parser withholds coordinates until both GGA and RMC show a valid fix at
the same UTC second and agree on position. It retains the last valid pair if
the receiver later loses its fix. No position has yet been measured. An outdoor sky-view
trial is needed before location can be reported. The current modules and
daemon bundle are RAM-only and vanish on reboot; V52 and the V50 rollback are
unchanged.

`tools/stage_august_gnss_bundle.py` verifies the exact stock bundle manifest,
then stages all files in `/run/lynx-gnss-static` with a full checksum pass.
It verified the already staged bundle on the current boot in
`logs/v52-gnss-bundle-stage-1793368222328223248/`. The path is stable for
later trials; it still disappears at reboot. The stock daemon also tried
Android assisted-position downloads and a debug service that are absent in
the RAM sandbox. These failures did not prevent NMEA output, but a cold fix
may take longer without assistance. The 20-second indoor trial cannot establish
whether the antenna and receiver can acquire satellites outdoors.

For the next physical test, place Lynx under a clear sky while keeping her on
Noobia Wi-Fi, then run `PYTHONPATH=tools python3 tools/trial_v52_gnss_mnld.py
--sky-trial` from `/noobia/lynx`. The prepared mode listens for up to 60
seconds, sends the stock stop command before its timeout, records the NMEA
summary, checks Alpine health, and uses a 115-second reboot guard if contact
or cleanup fails. Report coordinates only when `position_fix` is true in the
local summary. Do not run this command if Lynx has rebooted since the RAM
module staging above; restage those prerequisites first. Run
`PYTHONPATH=tools python3 tools/stage_august_gnss_bundle.py` to restore the
userspace bundle on a later V52 boot.

### Bluetooth link and factory identity, 2026-10-30

Nexus discovered Lynx's LE advertisement and subsequently completed a direct
Bluetooth connection to the V52 controller. Lynx observed the disconnect
event, the firmware path was restored, and Alpine remained healthy. This
earlier raw-HCI trial had no GATT or NRP/1 service. Evidence:
`logs/v52-bluetooth-hci-1793365652678716069/`.

The controller currently reports a MediaTek placeholder address beginning
`00:00:46`. Lynx's `nvdata` partition (`/dev/sdc10`) is ext4; it was mounted
briefly with `ro,noload,nosuid,nodev,noexec` and unmounted. The first six
bytes of `APCFG/APRDEB/BT_Addr` contain a different factory address. Keep its
full value private in the local trial record. The matching MediaTek source
implements HCI vendor command `0xFC1A` with the factory bytes reversed in the
packet. A guarded V52 trial applied that command to controller RAM, read the
factory address back, and then Nexus connected to Lynx under that address.
Closing `/dev/stpbt` ended the test; no partition was changed. Receipts:
`logs/v52-bt-factory-address-1793365780727214907.json`,
`logs/v52-bluetooth-hci-1793365919207477246/`, and
`logs/v52-bluetooth-hci-1793365936598246700/`. The temporary HCI address
setting is proven; persistent Bluetooth service and NRP/1 transport remain to
be built.

### Standard Linux HCI and BlueZ trial, 2026-10-30

The V52 kernel has built-in `CONFIG_BT_HCIUART=y` and H4 support. Alpine did
not mount `devpts`, so `tools/trial_v52_bluetooth_hci.py --hciuart-bridge`
mounts a fresh `devpts` only inside a private mount namespace. Its bounded
`tools/lynx_stpbt_hciuart_bridge.py` forwards H4 bytes between stock
`/dev/stpbt` and a PTY whose slave uses the kernel `N_HCI` discipline. No
kernel rebuild, flash, or persistent service is involved. The first attempt
failed at PTY creation with `ENODEV`; the private `devpts` mount fixed that.
The ten-second bridge registered `hci0` and exchanged 445 host-to-controller
and 696 controller-to-host bytes. It closed cleanly, restored the firmware
path, and passed Alpine health. Receipts:
`logs/v52-bluetooth-hci-1793369211093551214/` and
`logs/v52-bluetooth-hci-1793369325547032064/`.

BlueZ initially saw no controller even though `hci0` existed in sysfs.
`tools/lynx_bt_mgmt_query.py` found the management index list empty. The
bridge's payload-free H4 trace showed the kernel sent
`Read Synchronization Train Parameters` (`0x0c77`) and the controller
returned status 1, unknown command. The matching kernel source includes that
request when page 2 of the extended features has byte 0 bit 2 set. Lynx's
controller advertised page 2 byte 0 as `0x05`, incorrectly claiming that
feature. The bridge now has an opt-in filter for **only** that bit in **only**
the successful page 2 `Read Local Extended Features` reply; every other
byte is forwarded unchanged. This makes the advertised capability match the
controller's actual command support. The local split-frame and no-payload
tests cover the filter.

With the filter, kernel management listed index 0 and BlueZ 5.86 recognized
the controller. A guarded `--bluez-power` trial powered it on after one
transient busy response during setup. The bridge applied exactly one feature
correction, all recorded HCI command statuses were zero, and the controller
reported `Powered: yes`. BlueZ and D-Bus were stopped afterward; firmware
path and Alpine health were verified, and the reboot watchdog was canceled.
Receipts: `logs/v52-bluetooth-hci-1793383847286131258/` and
`logs/v52-bluetooth-hci-1793383972239566870/`. The `bluez` package is now
installed on Alpine, but neither service is enabled at boot. Preserve the
bounded trial until a persistent bridge has independent rollback and battery
checks.

The same read-only factory-address receipt used for raw HCI was then applied
in controller RAM **before** registering `hci0`. BlueZ reported the matching
factory identity and `Powered: yes`; the one-bit feature correction, service
stop, firmware-path restoration, watchdog cancellation, and Alpine health all
passed. The full address stays in the private local receipt, not this document.
Evidence: `logs/v52-bluetooth-hci-1793384220435832808/`. It still disappears
when the bridge closes and is not an automatic boot service.

### Temporary NRP/1 GATT round trip, 2026-10-30

The live `lynx-noobd` now has a root-only local Unix socket in the same
process as the Wi-Fi NRP/1 endpoint. A bounded GATT application using that
socket registered successfully with BlueZ. Nexus scanned for Lynx's private
factory address, connected without pairing, resolved the dedicated service,
wrote `NRP/1 52 PING`, and read `NRP/1 52 OK PONG`. The client disconnected;
the application and bridge exited; BlueZ and D-Bus stopped; the firmware path
was restored; the watchdog was canceled; and Alpine health had no issues.
No boot partition write was made. The endpoint accepts only `PING` and `INFO`
until per-client state and authorization are added. It is disabled at boot.
Receipts: `logs/v52-noob-local-socket-1793386552572118101/result.json` and
`logs/v52-bluetooth-hci-1793387060460429646/result.json`.

The later passive OpenRC candidate install preserved `boot_a` and left the
service disabled. Two guarded start/PING/stop cycles on the same V52 boot
verified controller teardown, firmware path, Alpine health, and watchdog
cancellation. See [LYNX-BLUETOOTH-NRP.md](LYNX-BLUETOOTH-NRP.md) for receipts
and the remaining authorization and cold-boot work.
