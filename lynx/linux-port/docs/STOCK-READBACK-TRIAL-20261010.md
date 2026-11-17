# Lynx stock-loader readback trial, 2026-10-10

The guarded MTKClient probe was started with the archived DA_BR.bin and
auth_sv5.auth, stock mode and the printgpt command. The user powered/cycled Lynx
and reconnected without buttons; the phone resumed its existing Orange State
loop. The tool repeatedly reported `Handshake failed, retrying...`. Reviewing
Port.handshake shows that it also returns failure after waiting without finding
a device; those messages do not prove transient preloader connections. Kernel
USB events from the trial show the old Fastboot device disconnecting at 03:11,
with no subsequent phone enumeration. No chip identification or successful
loader upload was observed. No GPT or partition contents were obtained.

The probe was explicitly terminated; both the diagnostic process and its timeout
process exited. No flash, erase, format, slot switch or bootloader modification
occurred. The stock-loader readback/restoration route remains unverified.

Session directory:
`/noobia/lynx/tools/mtk-sessions/1791591007064726718`.

Do not infer that the phone's automatic restart loop was caused by flashing.
No Linux image was sent during this attempt. Further diagnosis should inspect
USB enumeration, serial-port contention and handshake logs before another
physical connection trial; do not escalate to exploitation or blind flashing.

ModemManager was active, but its journal had no trial-period entries. There is
no evidence at present that it caused the failure; it was not stopped or
reconfigured. The next prerequisite is confirming an actual low-level USB
enumeration, rather than assuming that an Orange State screen exposes one.
