# Lynx: observed buttons, power and USB sequences

Device: OnePlus Nord 3 CPH2493 / MT6983. These are observations from this
session, not a claim about every Nord model or every possible starting state.
No exact button-hold durations were measured. A black screen alone does not
prove power off; record the subsequent USB identity as well.

| Starting state | Sequence used | Observed result | Evidence / confidence |
| --- | --- | --- | --- |
| Orange State / restarting | USB connected; hold **Power + Volume Down** through the restart | User reached **Fastboot Mode**; host saw **0e8d:201c** | Repeated user reports and fresh identity checks. Latest recovery-entry preflight: `logs/restored-recovery-entry-1791650631909853604.json`. |
| Verified Fastboot | Computer sends fixed `fastboot reboot recovery` | Command accepted; recovery menu can take a long time past Orange State | `logs/restored-recovery-entry-1791650631909853604.json`; user reports recovery delay. Command acceptance alone does not prove the menu appeared on every attempt. |
| Stock recovery menu | Select **Power off**, then unplug USB | User reported phone off | User report before the first availability probe. Never select **Format data** for these diagnostics. |
| Orange State during delayed recovery entry | User pressed **Power + Volume Up** | Screen became black; user thought she was off | Physical power-off was unconfirmed at that moment. Subsequent button-held connection did reach preloader. Do not label black screen alone as a verified power state. |
| Reported off, USB unplugged; probe already waiting | Plug in USB **with no buttons held** | Phone entered Orange State; transient preloader handshakes failed; later user reported restarting | `tools/mtk-sessions/aio-readiness-1791650028679335198/`. No completed handshake or loader upload. User first reported no restart loop, then reported restarting; preserve that order. |
| Dark screen / believed off, USB unplugged; probe confirmed waiting | Hold **Volume Up + Volume Down**, plug USB **on Aria's explicit NOW signal**, do **not** press Power; keep both volume buttons held until capture is confirmed | **22d9:0006 OPLUS Preloader**, regular/preloader mode, MT6983 **0x907**; unchanged stock DA1/DA2 accepted into RAM; availability command answered | `tools/mtk-sessions/aio-readiness-1791650798290665979/`. This is the successful loader-entry sequence. Aria explicitly told the user to release both volume buttons after acquisition. No flash, exploit payload or session-authentication attempt. |

## Coordination for the successful connection

1. Phone has a dark screen after power-off action; USB is unplugged.
2. Aria starts the guarded probe and waits for its actual **Waiting for PreLoader** output.
3. Only then Aria says **connect NOW**.
4. Noob holds **both volume buttons**, plugs USB, and keeps holding them.
5. Aria confirms the host handshake identifies **MT6983 in regular/preloader mode**.
6. Aria tells Noob to release both volume buttons.

The process has a bounded waiting deadline. If the start signal becomes stale,
check the process is still waiting before reconnecting. Do not ask Noob to time
the USB connection against a process that has not actually started.

The tool's generic BROM hints are not the desired mode. The guard rejects BROM
or a chip other than MT6983. Do not conclude that holding both volume buttons
means BROM: this actual run identified **regular/preloader mode**.

## What this result means

The successful run proves a useful physical connection procedure and stock
loader-command availability. It does not prove a working native Linux boot,
authentication bypass, RAM exploit, partition readback, or crash-log extraction.
The current persistent boot_a is the verified restored stock image. The successful
probe left a stock loader running in RAM, awaiting a file that we deliberately
did not send; do not confuse that state with Fastboot or a powered-off phone.

See [availability results](AIO-READINESS-HANDSHAKE.md) and the saved session logs.

## Manufacturer guidance, separate from our observations

The [official Nord 3 manual](https://service.oneplus.com/content/dam/support/user-manuals/en/OnePlus_Nord_3_5G_User_Manual_EN.pdf)
specifies holding **Power + Volume Up for 10 seconds** to shut down a powered-on
phone, then pressing Power to start it again. This is manufacturer guidance;
the effect in the currently loaded maintenance program has not been independently
observed. It supports the user's earlier Power + Volume Up action, but does not
retroactively prove that any particular black-screen observation meant power off.

A reference copy is saved as `downloads/OnePlus_Nord_3_5G_User_Manual_EN.pdf`.
For our next native boot trial, first leave the temporary loader by this shutdown
sequence, then use the session-proven **Power + Volume Down** Fastboot entry.
If the expected mode does not appear, record the actual screen and USB identity
before trying another combination.

## Later Fastboot-entry correction

After leaving the RAM-loader session, the user reported Orange State. The
suggested Power + Volume Down sequence during that state did **not** produce
Fastboot. Do not present it as reliable from every Orange State or RAM-loader
transition merely because earlier attempts succeeded.

The user then reported waiting a long time for **stock recovery to appear**,
using **Volume Down + Power to start**, and reaching **Fastboot while USB was
unplugged**. The precise intervening power-off/menu action was not described;
do not invent one. This is a user-reported result awaiting fresh host confirmation.
Aria instructed the user to plug USB only after Fastboot was on screen and to
release the buttons. Stable Fastboot does not require the timed preloader
connect-NOW procedure.

Host confirmation followed: 0e8d:201c, expected serial/product, unlocked state,
slot A and matching bootloader were verified in the preflight referenced by
`logs/boot-a-usb-xhci-trial-1791652936719946783.json`.
This confirms the user's recovery-first procedure did reach real Fastboot,
not merely a similarly labelled screen.

## Both volume buttons from an active restart loop

After stock boot_a restoration, the user unplugged USB and reported that
Power + Volume Up did not keep Lynx off: Orange State and restarting continued.
The exact hold duration and physical key state were not independently observed.
Do not keep asserting that the manual's force-off recipe succeeded here.

With a header-only diagnostic already waiting, the user held both volume buttons
and connected USB during the restart loop. This time the user reported **Fastboot**,
and host confirmed **0e8d:201c**, node 001/016. The preloader-only probe correctly
did not acquire this Fastboot endpoint and was stopped before any memory read.
Session: `tools/mtk-sessions/pstore-header-1791653783841864580/`.

This is a different observed result from the earlier dark/off-start combination
that produced 22d9:0006 OPLUS Preloader. Starting state and timing are part of the
procedure; do not attribute the difference to user error or treat either combo
as universally selecting one mode. Aria requested stock recovery from verified
Fastboot so the recovery menu's **Power off** action could be used next.

The recovery-menu-powered-off start was subsequently repeated. Holding both
volume buttons while plugging in at the confirmed waiting signal produced
22d9:0006 OPLUS Preloader on node 001/017 and a regular MT6983 handshake with
matching chip identity. Evidence: `tools/mtk-sessions/pstore-header-1791654123980651167/receipt.json`.
The header probe stopped on a nonzero status before data reception; this does
not diminish the independently confirmed button/mode result. Buttons were
released after Aria confirmed acquisition.


## Full collector first live attempt

Session pstore-full-1791659369491056067: USB was absent before starting the probe. After the explicit connect cue, the user held both volume buttons and USB enumerated 001/018, 22d9:0006 OPLUS Preloader. The regular handshake never completed; repeated handshake failures were observed. Stopped verified PID60882 with SIGINT; process exit130 and receipt state stopped/KeyboardInterrupt. No fixed-region memory request, loader upload, authentication, bypass or partition write occurred. This combination reached Preloader but did not prove a fresh protocol state or a completed handshake. Detailed exceptions were hidden at the current logging level, so enabling preserved DEBUG logging before another attempt. USB remained connected after the user was instructed to release buttons.


## Ordinary pstore read result — 2026-10-10

The DEBUG attempt pstore-full-1791659570169672293 enumerated USB001/020 (22d9:0006), but startup synchronization received A0 instead of expected5F. Stopped PID61573 with SIGINT, exit130. Same physical connection then accepted a single ordinary GET_HW_CODE query (fd09070000); normal preloader identification matched MT6983 and the exact saved Lynx SOC_ID. This establishes that the connected phone was already command-ready, without authentication, bypass or loader upload.

Full-region READ32 (917504 bytes) and a separate 64-byte size check at 0x48090000 both echoed every request field exactly and returned leading status0x1000 before data. No RAM data was received. Receipts and raw protocol replies are in tools/mtk-sessions/pstore-full-1791659786746018581/ and pstore-full-1791659923281277745/. Consolidated evidence: docs/pstore-ordinary-read-result.json. The MTKClient status table names0x1000 CRYPTO_INIT_FAIL, but this generic label does not prove the exact proprietary preloader cause or justify authentication/bypass. Ordinary RAM access to this region is unavailable through the tested interface; stop repeating it without new evidence.

ModemManager was active and inspected the same ttyACM path. Scoped mmcli inhibition failed NotFound, leaving service state unchanged. Interference was not established as the cause. No background collector remains, no partition changed, and last persistent boot_a remains stock. User was told to release volume buttons and leave USB connected.


## Button-free proof observation

Trial boot-a-boot-proof-trial-1791662841074803432 instructed no button input. Original Fastboot001/021 disappeared after the host reboot; later passive observer found new Fastboot001/022. No manual input was reported. Mode bits changed0 to3 with software reset status0x2 and long-pressed reboot0. Exact return latency was not captured because the first observer expired. This is a controlled software-return result, not another button-entry recipe. Stock undo completed with no reboot.


## Human observation confirmed; BusyBox first

Noob explicitly confirmed that no buttons were touched and Lynx was in Fastboot after the trial. This closes the pending experimental-control question and strengthens the native-init software-reboot proof. On the next turn Noob requested that the result be documented and coding continue, then clarified BusyBox first. Current development milestone is a live BusyBox USB shell using the already compatible stock kernel; kernel rebuilding and distribution integration follow specific demonstrated needs. No new flash is authorized by mere build-tool output; existing scoped controlled-trial authorization and restoration checks continue to govern any trial.
