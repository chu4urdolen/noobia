# Lynx matching stock foundation and next Linux trial

The user expanded authorization to judged-safe flashing and authentication work
to recover Lynx and obtain native Linux, prioritizing recoverable hardware.
No authentication bypass was needed for the restoration recorded here.

## Completed matching boot-chain restoration

Fastboot accepted exactly four August reference images into slot A:
boot_a, vendor_boot_a, dtbo_a and vbmeta_a. Image hashes were checked against
the verified full OTA and AVB audit. The package's LK build matches the
observed bootloader; no LK or preloader image was written. No slot switch,
slot-B write, data formatting or verification-disable flags were used.
The original companion images could not be read back before replacement.

Offline readiness: logs/stock-boot-chain-1791640182050679386.json.
Successful writes and recovery reboot:
logs/stock-boot-chain-1791640196780904534.json.
The fixed restoration tool is tools/lynx_stock_boot_chain.py.

The user reported the recovery menu appearing after Orange State and a delay.
This demonstrates recovery startup on the restored foundation. It does not
prove that the old Android system is present or that native Linux has booted.
No spontaneous-reset conclusion was drawn from user button presses.
USB/ADB query found no phone USB or ADB endpoint:
logs/matched-recovery-adb-1791640399807268329.json.

vbmeta_system_a and vbmeta_vendor_a remain unmodified. An offline model shows
that hypothetical empty child metadata can be fatal, even with an unlocked
policy. See docs/chained-metadata-model.json. That is not a phone readback;
the subsequently working recovery menu is a reason to avoid speculative
additional metadata writes.

## Prepared Linux trial against the matching foundation

The supplier candidate remains byte-identical to the third trial artifact:
artifacts/busybox-August-suppliers/nord3-busybox-candidate.img,
64 MiB, SHA-256
20b76e5fee8e71ec703dfd37b6709c45f5b03c780a4bd40adb290ae998681fe5.
It reuses this exact stock kernel and carries native BusyBox init plus 33
matching stock modules, including watchdog and USB suppliers. Its LZ4 ramdisk,
partition-end AVB metadata, module insertion and interactive native PID 1
have passed offline validation/model/ARM VM checks.

The earlier phone trial used unknown companion images; this next trial uses
the restored matching DTB/vendor ramdisk/DTBO/verification foundation. That
is a materially different boot-chain state, not a claim that Linux will work.
Native Linux, USB networking, watchdog takeover and an SSH server are not
proven on physical hardware. Replacing generic init can affect recovery entry;
the exact stock boot_a undo remains ready.

tools/lynx_boot_a_matched_trial.py pins candidate and stock undo, verifies the
completed four-write baseline receipt and reference hashes, and runs fresh
identity/slot/size checks before a live write. Default mode is offline.
Offline readiness passed: logs/boot-a-matched-trial-1791640471606769530.json.
The matching-foundation Linux trial has not yet been executed.

Trial, within the user's expanded authorization, once physically in Fastboot:

```sh
python3 /noobia/lynx/tools/lynx_boot_a_matched_trial.py --flash-linux --reboot
```

Only boot_a changes. Failure undo, after physical return to Fastboot:

```sh
python3 /noobia/lynx/tools/lynx_boot_a_matched_trial.py --restore-stock
```

Exact stock undo image SHA-256:
a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995.
Companion partitions stay on the newly restored stock set, and slot B,
bootloader and calibration/data partitions remain outside the write scope.

Current physical action required: select Power off in recovery, then use the
previously successful Power + Volume Down sequence to enter Fastboot with USB
connected. Do not select Format data. Stop on unexpected recovery behavior.
