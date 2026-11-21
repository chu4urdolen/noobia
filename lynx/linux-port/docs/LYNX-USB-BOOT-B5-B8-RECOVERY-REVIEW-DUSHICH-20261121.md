# Lynx USB Boot Persistence (B5 + B8) — Recovery-Focused Independent Review

- **Reviewer**: Dushich (D6, per Gwyn round-3 queue, note #135)
- **Date**: 2026-11-21
- **Scope**: Banshee B5 (`20252f6`, USB MTU3 ACM cold-boot persistence design) and B8 (`b81f72f`, boot-ordering revision), i.e. `lynx/tools/usb/lynx-usb-gadget.initd`, `lynx_usb_boot_persistence.py`, `test_lynx_usb_boot_persistence.py`, fixtures, and `LYNX-USB-COLD-BOOT-PERSISTENCE-DESIGN-20261121.md`.
- **Method**: Fresh offline clone of `origin/main` at `b81f72f` (`git clone --no-local`); line-by-line review plus full USB suite and CLI runs. No phone contact, no Lynx writes.

## Verdict

**ACCEPT — B5 as design + B8 as the required change.** B8 implements exactly what Gwyn's round-3 review (note #133) required of B5: the gadget can no longer delay SSH, every driver/UDC operation is bounded, and the validator + tests pin the new invariant. Four **minor** findings below; **none can block or break SSH or Wi-Fi at boot**, and the disable switch and rollback both work from an SSH-only session.

## (a) Can any path block or break SSH or Wi-Fi at boot?

**No block path.** Evidence:

1. **Ordering**: `lynx-usb-gadget.initd:9-11` — `after bootmisc modules sshd`; no `before sshd`, no `need` of any network service. The validator enforces both directions (`lynx_usb_boot_persistence.py:56-64`): `ordering_must_declare_after_sshd` required, `forbidden_ordering_before_sshd` failing. In OpenRC semantics `after` is weak ordering, so the service cannot hold up `sshd` startup in either direction.
2. **Bounded operations** (B8): `modprobe`/`insmod` at 5 s each and UDC bind/unbind at 3 s via `/bin/busybox timeout` (initd:28-37, 67-72, 81-82). Worst-case added boot time ≈ 13 s, and only *after* `sshd` is in the runlevel.
3. **No break path**: all failure modes are soft — module-load failures fall through with `ewarn`, UDC-missing only warns, configfs/mkdir failures `return 1` (a per-service failure; no other installed service `need`s `usb-gadget`, and nothing is installed yet). MTU3 (`11201000.usb0`) is a separate controller from the WLAN driver (`wlan_drv_gen4m_6983`); nothing in the script touches Wi-Fi state. Wi-Fi SSH (`192.168.100.107:2222`) is the primary lifeline and remains untouched by every code path.

**Residual (minor)**: the configfs mount and the descriptor `echo`/`mkdir`/`ln` steps (initd:39-65) are not wrapped in timeouts. These are local VFS/configfs syscalls — negligible hang risk, but see M2.

## (b) Do the disable switch and rollback work from an SSH-only session?

**Yes.**

- **Disable switch**: `touch /etc/lynx/disable-usb-gadget` is a pure filesystem op; the switch is checked in both `start_pre()` (initd:14-19) and `start()` (initd:21-24) and makes the service a successful no-op — no module, no configfs dirs, no UDC bind. Re-enable is `rm -f`. Both reachable over SSH; no local console needed.
- **Rollback**: `rc-update del lynx-usb-gadget default` + switch (design doc §6). `rc-service lynx-usb-gadget stop` unbinds with a 3 s bound (initd:77-96). All local syscalls, all reachable over SSH.
- **No bootloader mutation**: neither `boot_a` nor `vendor_boot_a` is touched; stock kernel, initramfs, and fastboot fallback stay intact (doc §6).

## Findings (all minor, none safety-blocking)

- **M1 — doc/script mismatch on soft-fail.** Doc §3.1.4 states failures "exit cleanly (`return 0` soft-fail)", but the script `return 1`s on configfs-mount or `mkdir` failure (initd:41-48) and `eend $?` (initd:74) reports service failure when the UDC bind times out. The safety property still holds (OpenRC treats service failure as non-fatal here, and SSH is unaffected) — but the doc and script should agree on wording ("reported as failed, never halts the runlevel or SSH").
- **M2 — unbounded configfs mount / descriptor writes.** For full B8 boundedness, wrap `mount -t configfs` (initd:40-45) and, if desired, the descriptor block in `timeout` as well. Recommended, not required.
- **M3 — weak validator timeout check.** `lynx_usb_boot_persistence.py:79-80` passes if the bare word `timeout` appears anywhere (even a comment). A regex for actual bounded invocations (`timeout -t <N>` on the modprobe/insmod/UDC lines) would be stronger.
- **M4 — (info) failure signalling.** A UDC-bind timeout marks the service start as failed (`eend 124`) — a useful signal; the doc should say explicitly that boot and SSH continue regardless.

## Verification evidence (fresh clone at `b81f72f`)

- `python3 -m unittest discover -s . -p 'test_*.py'` in `lynx/tools/usb/`: **32 tests, OK** (8 collector + 9 NRP transport + 15 boot persistence, incl. `test_reject_before_sshd`, `test_require_after_sshd`, `test_missing_bounded_timeouts`).
- CLI: `lynx_usb_boot_persistence.py fixtures/boot-persistence-valid-enabled.json --init-script lynx-usb-gadget.initd` → `PERSISTENT_ENABLED`, `is_valid=true`, no failures.
- Platform identity in fixtures/docs: Nord 3 CPH2493 / MT6983 / 22823 — consistent, no stale 11R/MT6895 in these files.
- Status: **not installed** on Lynx; Aria owns live trial execution and deployment (doc safety boundary §1).
