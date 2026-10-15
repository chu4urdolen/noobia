# Ordinary diagnostic-header read

The stock loader availability capture advertises Mem read auth false. This is a
new ordinary-interface lead, not proof that any RAM read works. The interface
is distinct from download-agent session authentication; no authentication bypass
or download-agent upload is required by the prepared diagnostic.

`tools/lynx_preloader_pstore_header.py` reads exactly 64 bytes at 0x48090000,
the crash-log RAM region reported in Lynx's saved bootloader logs. It first
verifies regular MT6983 preloader mode and exact chip identity from the prior
successful Lynx session, and checks that the advertised memory-read authorization
flag is false. It uses the ordinary read-word protocol directly, with strict
echoes, leading/trailing status zero, exact 16-word count and bounded deadlines.
It accepts no user-specified address, length or alternative command.

Source is pinned by the existing manifest. Handshake setup disables automatic
watchdog manipulation in configuration and blocks unexpected memory/register
writes, uploads, authentication, BROM resets and bypass methods. No generic
MTKClient peek/read CLI or loader initialization is executed. Host metadata and
the preserved header/receipt stay inside Lynx's directory. The live command has
not run yet; offline tests verified one exact request and six abort cases.

Default invocation prints an offline plan. `--self-test` uses mock protocol
responses without USB. `--connect` requires the recorded, synchronized,
both-volume-buttons preloader entry. It waits at most three minutes, then bounds
active work to thirty seconds after handshake. A denied or malformed response
ends the diagnostic, without fallback. Even a successful header read would not
identify the crash-record age or prove a native Linux boot.

The latest native trial failed to expose USB; verified stock boot_a restoration
completed before this probe was prepared. Lynx was left in Fastboot. No direct
RAM read, authentication bypass or exploit payload was executed during preparation.

## First connection attempt

Session `tools/mtk-sessions/pstore-header-1791653783841864580/` started, but
the user could not keep the phone off with the force-off buttons. Connecting
with both volume buttons during the restart loop led to user-reported Fastboot,
confirmed by 0e8d:201c on host node 001/016. The preloader-only filter excluded
that endpoint. No MT6983 handshake or diagnostic read completed. The waiting
process was stopped by SIGINT and exited with status 130; receipt preserved.
This attempt did not test memory-read access. A powered-off recovery-menu start
is the next physical prerequisite before repeating the prepared ordinary read.

## Second connection and status-handling correction

After the user powered off through recovery and reconnected with both volume
buttons at the explicit signal, host saw 22d9:0006 OPLUS Preloader, node 001/017.
Session `tools/mtk-sessions/pstore-header-1791654123980651167/` identified regular
MT6983 and matched Lynx's chip ID. It attempted the fixed 64-byte header request,
then stopped on its leading-status check. No header file, loader upload, write,
authentication attempt or bypass followed. The user was told to release the buttons.

The initial guard required exactly zero but the pinned ordinary-read implementation
accepts status values 0..0xff. The original guard did not record the actual nonzero
status. Its message "read denied" therefore does **not** establish an authentication
block: it could have rejected a status accepted by the source implementation.
That mistake and its uncertainty are preserved rather than retroactively labelling
the failed probe successful. The original tool remains unchanged for reproducibility.

A separate corrected tool `tools/lynx_preloader_pstore_header_status.py` accepts
only the source implementation's low status range, saves leading and trailing
status values, and logs the waiting handshake to a local file instead of flooding
the user-facing tool output. It retains the exact address/size, chip identity,
authorization-bit requirement, timeout, and all write/upload/authentication blocks.
Offline tests cover zero and low nonzero statuses, status capture, and eight abort
cases. It has not yet run live. A fresh physical session is required before retry;
do not reuse the protocol state from the incomplete request.
