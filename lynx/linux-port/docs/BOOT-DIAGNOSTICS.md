# Lynx boot diagnostics, 2026-10-10

No partition flash was performed during this investigation. Stock boot_a from
the third-trial undo remains the last image written. Slots and companion
partitions were not changed.

## Working log export

The verified stock LK contains the exact command string oem dump_pllk_log.
The protocol client source at https://github.com/R0rt1z2/dump_pllk_log was
inspected and preserved under sources/pllk-log-reference with source hashes;
that external client was not executed. Our fixed-serial guarded diagnostic
is tools/lynx_pllk_log.py. Default invocation prints a plan; --connect first
checks identity/slot and then sends only the log export command. No flash,
erase, reboot or unrelated OEM command is allowed by this tool.

The OEM bootloader is proprietary; full firmware side-effect semantics have
not been proven by reverse engineering. The recognized command and inspected
client establish it as a diagnostic log-export interface, not a partition
restore or firmware upload operation.

Capture succeeded: logs/pllk-1791605737142452962.json.
Raw output: logs/pllk-1791605737142452962.raw.txt, 320335 bytes.
Cleaned reconstruction: logs/pllk-1791605737142452962.clean.txt, 185887 bytes.
The first line-only decoder lost embedded-newline continuations; its output
was preserved as .previous-line-decoder.txt. The corrected decoder removes
only INFO framing; synthetic boundary tests at 1, 3, 7 and 20-byte packet
sizes retained embedded CRLF/LF content. Raw output remains authoritative.
Full logs stay local; they may contain device-specific identifiers.

The capture covers the current preloader/LK session and Fastboot entry, not
an observed failed-kernel handoff. It records bootloader recovery of saved
SYS_PSTORE_RAW from expdb offset 0x3000, size 0xe0000, and SYS_RAMCONSOLE_RAW
from offset 0x2000, size 0x1000. It reports watchdog status fields 0 and 0x2404
in current/restored contexts. Record age and reset cause are unknown; do not
label these fields as proof of our trial's watchdog failure. These records
are pointers to possible evidence, not retrieved kernel logs.
See docs/boot-diagnostics-audit.json for line references.

## Stock recovery diagnostic attempt

Fresh preflight passed. Fastboot accepted reboot recovery, without any
partition write command. Receipt: logs/stock-recovery-probe-1791605856194931851.json.
The user reported Orange State staying on screen. A bounded 30-second
USB/ADB observation saw neither phone USB nor ADB access; no ADB shell
command was sent. Receipt: logs/recovery-usb-adb-1791605895940577303.json.

The recovery attempt was stopped, with no automatic follow-up reboot, flash,
format or workaround. The user was instructed to return physically to
Fastboot. Recovery shell access and stock recovery startup remain unproven.
The user returned Lynx to Fastboot. Read-only preflight passed after granting
access to the new USB node /dev/bus/usb/001/030; receipt:
logs/fastboot-preflight-1791606521435767557.json. No new partition writes occurred. The native Linux goal is unchanged.

## Next diagnostic boundary

Preserve the existing log tool and verified images. The useful next evidence
would be the saved expdb/pstore records or an early hardware console. Fetch
and prior guarded MediaTek readback routes were unavailable; do not treat
log locations as authorization to modify expdb or bypass authentication.
Do not propose another stored Linux image merely because it boots in QEMU.

## Follow-up Fastboot log capture

Fresh log export succeeded after physical return from the recovery attempt:
logs/pllk-1791606541890396711.json, raw bytes 309489, reconstructed bytes 179518.
The comparison of raw boot/reset fields is preserved in
docs/boot-reset-record-comparison.json. Neither capture establishes retrieval
of the failed Linux kernel log; do not attribute old crash records to a trial.
Lynx is reachable in Fastboot and stock boot_a remains the last image written.
