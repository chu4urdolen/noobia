# Stock-loader availability probe: no completed handshake

Session: `tools/mtk-sessions/aio-readiness-1791650028679335198`.
The user powered Lynx off through restored stock recovery, disconnected USB,
and reconnected without buttons as instructed. The user then reported Orange State.
The user explicitly clarified that Lynx was not in a reboot loop. Treat the
screen as stationary Orange State; repeated host handshake failures do not
establish repeated phone reboots.
The user subsequently reported that Lynx had started restarting, then returned
her to Fastboot with Power + Volume Down. Preserve this as a later state change,
not a correction that retroactively makes the earlier stationary observation a loop.

The guarded process ran with USB access and detected transient preloader
connections, but reported handshake failure repeatedly. No fresh MT6983 handshake
completed, no DA1/DA2 upload success was reported, and the AIO command-availability
check was not reached. No new payload, authentication bypass, or storage write
was attempted. This result does not test whether the AIO command is supported.

The host process was stopped with SIGINT after verifying its PID and command.
It exited with KeyboardInterrupt/status 130; the session receipt and raw log
remain preserved. Last recorded boot_a is the restored verified stock image.

The next prerequisite is a stable preloader entry. Holding both volume buttons
while reconnecting previously produced 22d9:0006 OPLUS preloader and successfully
loaded the exact stock DA in an earlier session. That is the next physical
sequence to try, from powered off, with the guarded probe already waiting.
The guard still rejects BROM mode or a chip other than MT6983. The source's
general BROM hints are not instructions to change those limits.

## Button-held retry succeeded

Session `tools/mtk-sessions/aio-readiness-1791650798290665979` completed after
the user held both volume buttons while connecting. Lynx enumerated as
22d9:0006 OPLUS Preloader, and the guarded handshake identified MT6983,
hardware code 0x907, in regular/preloader mode. The user was told to release
the volume buttons after successful acquisition.

Exact unchanged stock DA1 and DA2 were uploaded to RAM successfully. The
short-filename SECURITY-SET-ALLINONE-SIGNATURE request returned a DwnFile
request for lynx-aio-readiness.bin, packet length 2097152. No signature or
exploit payload bytes were provided. The process then exited successfully.
No session authentication, security bypass, or storage command was attempted.
The guarded tool skips the upstream printgpt dispatch implementation.

This demonstrates availability of the required loader command, not working
heap exploitation or crash-log readback. The device may await the requested
file in its RAM loader. A power cycle is required before another fresh guarded
session; do not infer that Fastboot is currently active. Stock boot_a remains
the last recorded persistent boot image.
