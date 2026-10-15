# Stock table request not acknowledged

Corrected live session: `1791597375560105517`, preserved under
`tools/mtk-sessions` with `probe-output.log`.

The physical sequence succeeded. Preloader handshake and MT6983 identification
completed, and both unchanged stock loader stages started in RAM. The direct
READ-PARTITION-TABLE request returned False from send_command. The wrapper
recorded `Partition-table command acknowledgement: False` and raised
`Partition-table command was not acknowledged: False` before requesting a table
transfer. It exited with status 1, without automatic fallback.

False is not an explicit device error code: upstream send_command also uses it
for transport failure or an unsupported/unrecognized reply. Therefore this does
not prove a particular authentication refusal or damaged on-device GPT. It does
establish that this tested stock path did not produce an acknowledged metadata
read. No table or partition backup was obtained.

No patched loader, Linux image, storage write, erase or slot switch was used in
this attempt. The handset is left in a RAM diagnostic state and needs a power
cycle to return to normal bootloader startup. Do not repeat the same physical
sequence without a new protocol finding or a different validated readback path.

Known working: Fastboot return, slot queries, preloader handshake and signed
stock RAM-loader startup. Still unverified: usable partition readback, stock
restoration, recovery preservation after replacing boot init, native Linux boot.
