# Lynx: omitted I2C clock provider

The stock-metadata diagnostic reached no native USB console in its observation
window. The user reported Orange State; a spontaneous restart was not reported
for that specific test. Its image remains installed pending Fastboot return.

The stock compiled device tree's /i2c@11e01000 node supplies its main clock
through phandle 2, specifier 1. Phandle 2 resolves to /syscon@11E03000,
compatible mediatek,mt6983-imp_iic_wrap2. The matching stock module
clk-mt6983-imp_iic_wrap.ko contains that exact compatible string. The preserved
OnePlus source matches it in an OF driver table and registers the clock provider.
It depends on clk-common.ko. It was omitted from the 33-module native load list.

The earlier alias-based audit missed it because the stock module's modinfo
contains no OF aliases. That omission in our audit is corrected by independent
FDT, stock binary and driver-source checks. Evidence:
docs/i2c-clock-provider-audit.json and
sources/early-boot-reference/drivers/clk/mediatek/clk-mt6983-imp_iic_wrap.c.
Actual driver binding on the phone remains unproven.

prepare_stock_metadata_candidate.py --include-i2c-clock creates a separate
34-module variant, ordering the clock providers before the I2C bus driver.
Native init, BusyBox and stock kernel are unchanged. The original OEM-signed
metadata/footer are retained, with the deliberate native-payload hash mismatch
described in STOCK-METADATA-DIAGNOSTIC.md. No OEM approval of the custom payload
is claimed. Required vendor modules are hash-bound to the matching stock archive.

Candidate: artifacts/busybox-August-stock-metadata-clock/nord3-busybox-candidate.img.
Size: 64 MiB. SHA-256:
c30423c1ba4489e9866ec49f74ae981e3868e5986affb1aa91122244ee71337d.
Independent validation passed. Unlocked AVB model loading and locked rejection
controls passed; docs/stock-metadata-clock-avb-model.json. All 34 module
insertions and native PID 1/shell startup passed in the isolated ARM VM;
artifacts/emulated-stock-metadata-clock and docs/clock-module-emulation-audit.json.
The emulator still does not model physical MT6983 clock or USB binding.

Offline readiness: logs/boot-a-clock-trial-1791642219120724699.json.
Within the user's expanded authorization, after physical Fastboot return:

```sh
python3 /noobia/lynx/tools/lynx_boot_a_clock_trial.py --flash-linux --reboot
```

Only boot_a changes; matching companion images and slot B stay in place.
If the trial fails, physically return to Fastboot and use:

```sh
python3 /noobia/lynx/tools/lynx_boot_a_clock_trial.py --restore-stock
```

Stock boot_a undo SHA-256:
a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995.
No hardware execution of the 34-module variant has occurred yet. Current
required human action is to return Lynx to Fastboot, retaining USB connection.

## Hardware test

The 34-module clock variant was written to boot_a and rebooted; receipt:
logs/boot-a-clock-trial-1791642317021085038.json.
The initial attempt stopped during preflight because of USB access permission;
no write was issued in that attempt. A completed passive observation found no
native USB console: logs/lynx-usb-observation-1791642332343276332.json.
Hardware boot is unproven; no stock undo has been issued for this test yet.
The next separately prepared variant removes the custom-argument startup gate;
see ALWAYS-USB-DIAGNOSTIC.md.
