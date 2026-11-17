# Full ordinary pstore capture readiness — 2026-10-10

User requested complete acquisition and preserved evidence to reduce repeated physical cycles.

The new tool `tools/lynx_preloader_pstore_capture.py` requests exactly the known pstore RAM allocation at `0x48090000`, length `0xe0000` (917504 bytes), through a single ordinary READ32 transaction. MT6983 regular preloader mode, the previously recorded exact SOC_ID, memory-read authorization flag, and pinned diagnostic source hashes are checked before the request. Loader uploads, authentication, security bypass, register/memory/storage writes and fallback routines remain blocked. Protocol commands necessarily travel over USB; they are read requests, not memory writes.

The capture stores raw big-endian wire words, decoded little-endian memory bytes, protocol replies, numeric leading/trailing statuses, request echoes, per-fragment timing, SHA256 hashes and partial results. A fragmented final word remains in the raw file and is recorded separately. The SDK aggregate reader can discard partial replies on timeout, so the transfer uses direct bounded endpoint reads. This is an application-level capture, not a complete USB bus trace. Handshake console output is preserved separately.

Twelve offline cases passed, including full-region capture, fragmented replies, accepted low nonzero statuses, rejected leading/trailing statuses, interrupted body and completion reads, three failed echo stages, and an oversized response. All mock session artifacts are retained in `tools/test-artifacts/pstore-offline-tests-1791659269535613359/`, with machine-readable `test-results.json` and source hashes.

No live run of this full collector has occurred. Hardware support for this single large request is unproven. A rejected request ends without another technique. Successful transport would not establish pstore age, decode compressed records, or prove association with the failed native boot.

Lynx currently enumerates as 22d9:0006, USB 001/017, from the earlier interrupted header request. Its protocol state is not assumed clean. A fresh physical preloader entry is required before live acquisition. No new flash or partition change was made during collector development. Last known persistent boot_a remains the verified stock undo recorded in logs/boot-a-usb-xhci-trial-1791653164047994118.json.


### Earlier header probe correction

The earlier live header session `tools/mtk-sessions/pstore-header-1791654123980651167/` completed the regular MT6983 handshake and exact chip identity match, then stopped on a nonzero leading status before saving any header. The numeric status was not preserved. The pinned upstream implementation accepts statuses 0 through 255; the original probe incorrectly required zero. Therefore its “denied” error is not evidence of confirmed authorization denial. The new collector records the actual status, uses the documented range, and never falls back to authentication or bypass.

The immediately preceding both-volume-button attempt from an active restart loop entered Fastboot instead. A later recovery-menu Power off, unplug, then both-volume-button connection reached OPLUS Preloader. These are distinct initial states; the combination is not guaranteed to select the same mode from every state.


## Ordinary pstore read result — 2026-10-10

The DEBUG attempt pstore-full-1791659570169672293 enumerated USB001/020 (22d9:0006), but startup synchronization received A0 instead of expected5F. Stopped PID61573 with SIGINT, exit130. Same physical connection then accepted a single ordinary GET_HW_CODE query (fd09070000); normal preloader identification matched MT6983 and the exact saved Lynx SOC_ID. This establishes that the connected phone was already command-ready, without authentication, bypass or loader upload.

Full-region READ32 (917504 bytes) and a separate 64-byte size check at 0x48090000 both echoed every request field exactly and returned leading status0x1000 before data. No RAM data was received. Receipts and raw protocol replies are in tools/mtk-sessions/pstore-full-1791659786746018581/ and pstore-full-1791659923281277745/. Consolidated evidence: docs/pstore-ordinary-read-result.json. The MTKClient status table names0x1000 CRYPTO_INIT_FAIL, but this generic label does not prove the exact proprietary preloader cause or justify authentication/bypass. Ordinary RAM access to this region is unavailable through the tested interface; stop repeating it without new evidence.

ModemManager was active and inspected the same ttyACM path. Scoped mmcli inhibition failed NotFound, leaving service state unchanged. Interference was not established as the cause. No background collector remains, no partition changed, and last persistent boot_a remains stock. User was told to release volume buttons and leave USB connected.
