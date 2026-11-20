# Lynx NFC preflight — 2026-11-20

This is a read-only checkpoint on V53 Alpine boot
`0fe847d2-44d6-4ac1-9000-2c99df1a51d8`. No NFC module was loaded, radio
enabled, sysfs attribute written, or service changed.

## Evidence

- The active platform node `/sys/bus/platform/devices/odm:nfc_chipset` has
  compatible `oplus-nfc-chipset` and two device-tree strings named
  `chipset-21871` and `chipset-22823`, both `SN110T`. They describe the
  selected platform configuration; they do not prove the installed chip
  answered.
- The platform node has no bound `driver`. No NFC-named I²C device or
  `/dev/nq-nci` appeared in the read-only inventory, and the bounded kernel
  log search returned no NFC probe line.
- Stock `init.SN100x.nfc.rc` expects `/dev/nq-nci`. The matching August stock
  package has `oplus_nfc.ko` (SHA-256
  `4ab0e019dceb426f8bf435a8ea21a40f71ec3f7809441a78e997f37fdd34f940`,
  dependency `oplus_project`) and `nfc_i2c.ko` (SHA-256
  `042f949ba0b4ddf5ee4d1ae143be407d1df1cc5be53518cce43e13c1acb67896`,
  no declared module dependencies). Both advertise V53's exact
  `5.10.149-android12-9-o-g311738fbb5a8` vermagic. `oplus_project` is
  already loaded on this boot.

## Next gate

The next live step is a guarded RAM-only module probe with fresh boot/image
identity, at least 50% battery, safe temperature, healthy Wi-Fi/SSH, a timed
reboot fallback, and an attended physical recovery path. Stage the exact
modules under `/run`, verify hashes and vermagic again, load one at a time,
and record timing, kernel messages, driver binding, expected node, and health
after each step. A node or bound driver alone will not validate NFC exchange.
Do not start an Android NFC HAL or perform a transaction as a status probe.
`lynx/tools/trial_v53_nfc_ram.py` is prepared for that step. Its default mode
checks the exact stock module hashes and kernel ABI without contacting Lynx;
`--start` requires the fresh live guards, stages only in RAM, records each
command and elapsed time, and arms a timed reboot fallback before loading.
**2026-11-21 guarded RAM probe:** Noob attended the recovery window. The
script's offline hash and ABI checks and three offline tests passed; fresh
Alpine health reported 100% and charging, 38.1°C maximum thermal zone, clear
health, and the expected V53 boot. The live script loaded `oplus_nfc` and
`nfc_i2c` from verified `/run` copies after arming a 120-second reboot
watchdog. Both loads returned successfully. The platform driver bound,
`/dev/nq-nci` appeared, and the kernel's `nfcc_hw_check` logged a returned
GET_VERSION response (`Chip Type 0xa4`, ROM `0x01`, firmware `0x10.68`). This
is evidence of chip communication during driver probe, beyond device-node
creation. No tag or peer transaction was attempted. Health and Wi-Fi remained
clear on the same boot; the watchdog was canceled. Only RAM staging was used,
so this driver state will disappear on reboot. Receipt:
`lynx/logs/v53-nfc-ram-1795213467857550302/result.json` and its step logs.

Next: design a bounded, attended NFC transaction that identifies an actual tag
without installing an Android HAL blindly. Keep the agent's `validated` flag
false until that succeeds. Do not start a service automatically from this
driver-probe result.
