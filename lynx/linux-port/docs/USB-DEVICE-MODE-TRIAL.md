# Primary USB peripheral-role diagnostic

The previous unconditional-startup trial wrote boot_a successfully (receipt
`logs/boot-a-always-usb-trial-1791643284225147093.json`). Its 60-second passive
observation saw no phone USB endpoint (`logs/lynx-usb-observation-1791643326304854339.json`).
There was no stock undo after that trial; it remains the last recorded phone image.
No physical native Linux boot marker has been observed.

The next candidate is `artifacts/busybox-August-usb-device-mode/nord3-busybox-candidate.img`,
SHA256 `6b76783a2cd9f2bcbbdb7b45bbc609786bf0e82a6f9376f180dc98703f37f577`.
It uses the unchanged stock August kernel and 34 exact matching modules. Its init
requests decimal mode 3 through the driver's primary-controller sysfs interface.
The request requires controller address 11201000, bound mtu3 driver, OTG mode,
matching compatible, usb-role-switch, no enable-manual-drd, and a registered
role-switch whose parent is that controller. It never requests host mode or writes
raw registers. The guarded request is retried during the bounded UDC wait.

Reference: [OnePlus published USB driver](https://github.com/OnePlusOSS/android_kernel_5.10_oneplus_mt6983/blob/81ec42ad5e803be0cba619f9f7bb298db7d33d7b/drivers/usb/mtu3/mtu3_dr.c).
This source maps DEVICE to 3 and uses the registered role-switch handler.
The stock base DTB meets the guards; actual selected DTBO and physical driver
binding remain unobserved. Stock module symbols and format strings support the
source correspondence, but do not establish binary identity with the source build.

Offline evidence: `usb-device-mode-guard-tests.json` (12 cases),
`usb-device-mode-arm64-validation.json` (exact kernel/ramdisks execute PID1,
34 modules, interactive ARM64 shell without custom USB boot argument),
`usb-device-mode-avb-model.json`, and independent image validation.
The VM has no physical MT6983 USB controller, so it cannot prove role switching.
Original OEM boot metadata remains unchanged, with an intentionally mismatched
native payload hash. Upstream AVB loads boot data under the unlocked model and
rejects it under the locked model; OnePlus LK behavior remains unproven.

The fixed tool `tools/lynx_boot_a_usb_device_mode_trial.py` verifies the candidate,
matching stock undo, full OTA verification, prior matching stock-chain restoration,
and fresh serial/product/unlock/slot/size checks before any write. Default execution
is offline readiness only. `--flash-linux --reboot` writes boot_a and reboots once;
`--restore-stock` writes the matching stock boot_a and leaves Fastboot available.
No slot switch or companion partition write is part of this trial.

Exact undo (after serial and slot-A checks):

```
/noobia/lynx/tools/platform-tools/fastboot -s 89BYAY5L4T9HFUOV flash boot_a /noobia/lynx/linux-port/artifacts/stock-cph2493-August-eu-ota/boot.img
```

At preparation time Lynx was reported on the Fastboot screen, but repeated host
USB inventories contained no phone endpoint. No new hardware write was issued.
Reconnect the cable while preserving Fastboot, identify the new USB node, then
use the fresh guarded preflight. Stop if recovery or USB transport behaves unexpectedly.

## Hardware trial result

After reconnection, Lynx enumerated as 0e8d:201c. Fresh identity, unlocked state,
slot A, bootloader version, partition sizes and 64 MiB download limit all matched.
The candidate write to boot_a and the subsequent reboot both returned OKAY:
`logs/boot-a-usb-device-mode-trial-1791644563194050978.json`.
No other partition was written during this trial.

The complete 60-second passive observation found no phone USB endpoint or ttyACM:
`logs/lynx-usb-observation-1791644574445277632.json`.
This does not distinguish failure before userspace from failure of USB setup.
No native hardware boot is proven. The device-mode candidate remains installed;
stock undo has not yet been performed. Next action requires the user to return
Lynx to Fastboot, then restore the verified stock boot_a and collect available
read-only boot logs before preparing further hardware trials.

## Stock undo and log acquisition

The user returned Lynx to Fastboot. Fresh guarded preflight passed and stock
boot_a restoration returned OKAY; no reboot or other partition write followed:
`logs/boot-a-usb-device-mode-trial-1791645217241106203.json`.
This supersedes the preceding statement that the native candidate was installed.
Current last recorded boot_a is the verified August stock image.

Reviewed log export succeeded: `logs/pllk-1791645230944832823.json`,
312923 raw bytes / 181518 reconstructed bytes. Saved pstore CRC is now
0x68e2c9e7 and ramconsole CRC 0x77770d35. Both changed since the prior capture,
but their ages and causes remain unknown. No native PID1 marker or retrieved
Linux kernel log is established. Reset fields remain 0 / restored 0x2404;
the earlier logo error remains present. See `usb-device-mode-reset-comparison.json`.
