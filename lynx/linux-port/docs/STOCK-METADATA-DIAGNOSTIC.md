# Lynx boot-metadata diagnostic

The matching-foundation native image still restarted without a USB console.
Stock boot_a was restored and final Fastboot checks passed. A subsequent log
capture shows different pstore/RAM-console checksums, but record age and reset
cause are not proven. The logo-table error appears in an older capture too;
its existence cannot be attributed to the latest companion-image restoration.
See `matched-trial-reset-comparison.json` and the preserved raw LK logs.

## Distinction being tested

Earlier native images use boot-local algorithm NONE metadata. This diagnostic
retains the exact original RSA2048 stock metadata and footer, including the
stock public key. Its modified native payload deliberately does not match the
original stock hash. It does not claim OEM approval or a valid OEM signature
for the modified Linux image. An unlocked verification-error policy is still
required. The goal is to distinguish metadata-format/key acceptance from
subsequent native startup, not to declare the device's actual AVB behavior proven.

The native payload fits entirely within the old stock hash descriptor's
21,889,024-byte coverage. Nine module copies are omitted from generic RAMdisk
and resolved from the now-matching stock vendor RAMdisk. All 33 loaded module
byte sequences and native init remain the same as the supplier experiment.
Legacy-LZ4 compression matches the stock vendor archive. Bootloader and slot B
are outside the write scope; no root vbmeta flags are altered in this test.

Candidate: artifacts/busybox-August-stock-metadata/nord3-busybox-candidate.img,
64 MiB, SHA-256:
186008a96fc5f71974167c798c3bf79c3c67e06a2418d1b69c8fd53ff5bc2bb8.
Stock boot_a undo SHA-256:
a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995.

## Checks completed

- Independent validator checks preserved stock footer/blob/signature, expected
  modified-data hash mismatch, static BusyBox, native init and 33 module ABIs.
- Actual upstream AVB host model loads boot under unlocked policy with
  ERROR_VERIFICATION and rejects it under the locked-policy control. This is
  not OnePlus LK execution and assumes a trusted stock root and rollback zeros.
- Exact kernel plus concatenated stock-vendor/native archives boot in the ARM
  VM. All 33 modules insert successfully, PID 1 stays alive and the shell runs.
  The VM does not emulate MT6983 peripheral binding or a physical watchdog.

Evidence: docs/stock-metadata-avb-model.json,
artifacts/emulated-stock-metadata-startup/{console.log,result.json}, and
logs/boot-a-metadata-trial-1791641779638937322.json.

## Guarded commands within expanded authorization

The fixed tool checks this exact candidate and stock undo, matching baseline
receipt and reference hashes, exact VM/model evidence, independent validation
and fresh serial-bound Fastboot preflight. Default mode is offline.

```sh
python3 /noobia/lynx/tools/lynx_boot_a_metadata_trial.py --flash-linux --reboot
```

Only boot_a changes. If no stable native console appears, physically return
to Fastboot and execute the prepared stock undo:

```sh
python3 /noobia/lynx/tools/lynx_boot_a_metadata_trial.py --restore-stock
```

Do not conflate unchanged metadata-signature validity with native payload
authenticity or hardware success. The bootloader stays unlocked. No factory
reset, slot switch, lock/unlock, preloader/LK/calibration write or MTK DA exploit
is part of this test. Stop for required human interaction or unexpected recovery.

## Hardware observation

The diagnostic was written to boot_a and rebooted once; receipt:
logs/boot-a-metadata-trial-1791641812798958182.json.
No USB console appeared during the completed passive observation:
logs/lynx-usb-observation-1791641831182897450.json.
The user reported Orange State remaining visible. A spontaneous restart was
not reported for this specific test. Native hardware boot is unproven.
No stock undo has yet been issued; this diagnostic image is still installed.
A subsequently confirmed missing I2C clock provider is addressed in the
separate 34-module variant described in I2C-CLOCK-FIX.md.
