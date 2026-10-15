# Lynx: unconditional watchdog and USB startup

The 34-module clock-provider image produced no native USB console in its
completed observation window. Actual kernel command-line delivery remains
unknown. The original native init placed both watchdog module insertion and
USB setup inside a noobia.usb=1 condition. That is an unnecessary dependency
for this diagnostic image and could suppress our only observation channel.
There is no evidence yet that Lynx's bootloader actually dropped this argument.

A separate source, init-usb-always, retains the original native init flow but
makes the module/USB block unconditional and logs the actual /proc/cmdline.
The original init and all prior images remain preserved. No partition mounts
or storage-writing commands were added. The exact stock kernel, static BusyBox,
34 matching modules and clock-before-I2C ordering are retained.

Candidate: artifacts/busybox-August-clock-always/nord3-busybox-candidate.img.
Size: 64 MiB. SHA-256:
377e10008daa84aef31bcad5979bc98b780c620f4aaa7f543410a2b064884d15.
It preserves stock boot metadata with the expected modified-payload hash mismatch;
see STOCK-METADATA-DIAGNOSTIC.md. It remains an unlocked experimental image,
not an OEM-approved payload.

Independent image validation passed. Exact kernel plus vendor/generic ramdisks
ran in ARM QEMU without noobia.usb=1: all 34 module insertions were observed,
native PID 1 stayed alive and interactive shell commands executed. The absent
physical controller was handled without exiting PID 1. Evidence:
artifacts/emulated-clock-always and docs/always-usb-arm64-validation.json.
Unlocked AVB model loading and locked-policy rejection controls passed;
docs/always-usb-avb-model.json. Physical MT6983 startup remains unproven.

Default offline readiness passed:
logs/boot-a-always-usb-trial-1791642903181882051.json.
Within the user's expanded authority, once Lynx is in Fastboot:

```sh
python3 /noobia/lynx/tools/lynx_boot_a_always_usb_trial.py --flash-linux --reboot
```

The fixed guard pins this image and exact stock undo, checks the matching stock
baseline and offline evidence, and runs fresh serial/identity/slot/size queries
before the only write, boot_a. No companion, bootloader, calibration or slot-B
write is part of this test. Failure undo after physical Fastboot return:

```sh
python3 /noobia/lynx/tools/lynx_boot_a_always_usb_trial.py --restore-stock
```

Stock undo SHA-256:
a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995.
The unconditional variant has not been flashed yet. The preceding clock variant
is still installed; no stock undo was issued after that preceding test.
