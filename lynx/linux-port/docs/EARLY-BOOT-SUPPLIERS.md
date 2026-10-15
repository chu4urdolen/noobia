# Lynx: watchdog and USB supplier investigation

After the second Linux trial rebooted without a USB console, stock boot_a was
restored and Lynx was left in Fastboot. This investigation made no phone calls
or partition changes. The observed reboot cause remains unconfirmed.

## Evidence

Stock modules.load includes mtk_wdt.ko; native startup's 24-module list omitted
it. Stock kernel configuration enables CONFIG_MEDIATEK_WATCHDOG=m,
CONFIG_WATCHDOG_HANDLE_BOOT_ENABLED=y and CONFIG_WATCHDOG_OPEN_TIMEOUT=0.
The selected OnePlus source checks WDT_MODE_EN, marks WDOG_HW_RUNNING and
registers the watchdog. The watchdog core then schedules a heartbeat for an
already running watchdog when boot handling is enabled. A bootloader-started
watchdog without its driver is therefore a plausible delayed-reset mechanism.
It is not established that the phone reached this point or had this timer enabled.

Preserved sources and SHA manifest: sources/early-boot-reference/.
Source commit: 81ec42ad5e803be0cba619f9f7bb298db7d33d7b; this is the published
selected Nord 3 reference, not a claim of exact reproduction of the stock binary.
The actual stock watchdog module has scmversion g311738fbb5a8 and SHA-256
e88eef609de96d7beabec96f4cb96d2b797801eef79184c727c6bc042d2eaa9d.
Its vermagic matches the exact reused stock kernel and it has symbol versions.
It declares no other module dependencies.

[Linux watchdog documentation](https://docs.kernel.org/watchdog/watchdog-parameters.html)
describes boot-enabled watchdog handling. We load the matching driver; no raw
register writes or watchdog-disable operation is proposed.

The stock compiled base FDT also exposes supplier drivers missing from the
native list: MT6375's I2C bus and parent PMIC, its ADC and charger, which supply
the USB role controller and extcon. Native module-symbol dependency closure
alone missed these device relationships. audit_early_boot.py preserves the
node paths, OF alias matches, phandle edges, candidate command line and caveats
in docs/early-boot-supplier-audit.json.

The audit uses the stock base FDT, not the installed DTB or applied DTBO.
Alternative/disabled controllers are included. Aliases are candidate matches,
not proof of driver binding. Actual hardware selection remains unknown.

## Separate offline diagnostic image

prepare_supplier_candidate.py preserves the second trial's kernel, boot header
command line, BusyBox and native init. It adds these nine stock modules and
their dependency order to a separate generic ramdisk:

- mtk_wdt.ko, loaded first
- mtk_boot_common.ko and i2c-mt65xx.ko
- mt6375.ko
- kfifo_buf.ko and industrialio-triggered-buffer.ko
- mt6375-adc.ko
- charger_class.ko and mt6375-charger.ko

Every added module is hash-bound to the verified stock vendor-boot audit, with
matching vermagic and symbol-version records. There are now 33 modules. The
ramdisk uses legacy LZ4 and boot has a partition-end, unsigned AVB footer with
flags zero. Existing tested images remain unchanged.

Candidate: artifacts/busybox-August-suppliers/nord3-busybox-candidate.img
Size: 67,108,864 bytes. SHA-256:
20b76e5fee8e71ec703dfd37b6709c45f5b03c780a4bd40adb290ae998681fe5.

Independent image validation passed. The unlocked-policy upstream AVB model
loads boot with its expected unsigned-metadata warning; the locked-policy
negative control rejects it. Basic combined-vendor/generic emulation passed.
An additional ARM VM run used noobia.usb=1 and actually executed all 33 insmod
operations and configfs startup. All load messages were observed with no
unknown-symbol or failed-module messages. PID 1 remained alive and reached
the shell after waiting for the absent physical USB controller.

Evidence: artifacts/emulated-suppliers-module-startup/{console.log,result.json}
and docs/supplier-module-emulation-audit.json. The VM has no physical phone USB,
MT6983 watchdog or peripheral buses: successful insertion does not prove
physical binding, watchdog takeover, USB networking or a phone boot.

## Third trial — authorized, executed, stock boot restored

Offline readiness passed, receipt:
logs/boot-a-supplier-trial-1791605152739963451.json.
The fixed-image tools/lynx_boot_a_supplier_trial.py checks both image hashes,
OTA verification, exact emulation evidence, AVB model and independent validation.
Live use checks serial, identity, slot and partition sizes again before any write.

After explicit authorization for this new image, the trial entry point is:

```sh
python3 /noobia/lynx/tools/lynx_boot_a_supplier_trial.py --flash-linux --reboot
```

Its only flash command is:

```sh
/noobia/lynx/tools/platform-tools/fastboot -s 89BYAY5L4T9HFUOV flash boot_a /noobia/lynx/linux-port/artifacts/busybox-August-suppliers/nord3-busybox-candidate.img
```

If the trial fails, return physically to Fastboot and restore stock boot_a:

```sh
python3 /noobia/lynx/tools/lynx_boot_a_supplier_trial.py --restore-stock
```

Exact undo:

```sh
/noobia/lynx/tools/platform-tools/fastboot -s 89BYAY5L4T9HFUOV flash boot_a /noobia/lynx/linux-port/artifacts/stock-cph2493-August-eu-ota/boot.img
```

Stock SHA-256: a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995.
Fastboot has accepted this undo after both earlier trials. No byte-for-byte
readback or recovery startup proof exists. Preserve bootloader, companion
partitions and slot B; stop on unexpected recovery behavior. There is no
display or SSH yet. Hardware success and guaranteed recovery remain unproven.

The user subsequently authorized this third trial. Fastboot accepted the supplier
image, but no Linux USB console appeared within 60 seconds. Stock boot_a was
restored and final identity/slot checks passed. See BOOT-A-SUPPLIER-TRIAL-RESULT-20261010.md.
The commands above are historical; they do not authorize another flash.
