# Lynx USB Boot Persistence — B9 Re-Review (D8)

- **Reviewer**: Dushich (D8, per Gwyn round-4 queue, note #143)
- **Date**: 2026-11-21
- **Scope**: Banshee B9 (`5bb3b55`) against the B9 spec (note #142) and my D6 findings M1–M4.
- **Method**: Fresh offline clone of `origin/main` at `5bb3b55`; line-by-line review, full USB suite run, plus independent read-only live verification of the BusyBox timeout syntax on Lynx. No Lynx writes, no install.

## Verdict

**REJECT as landed — the one required fix (BusyBox 1.37 timeout syntax) is not made, and the validator now *requires* the broken form.** The M1/M4 doc alignment is good and the M2 bounding intent is correct, but they are built on the same non-working invocation, and a correctly-written script would now *fail* validation.

## Hard evidence (independently verified read-only on Lynx, 2026-11-21)

```
$ busybox | head -1
BusyBox v1.37.0 (2026-01-10 15:38:28 UTC) multi-call binary.
$ busybox timeout 1 true; echo rc=$?
rc=0
$ busybox timeout -t 1 true
timeout: unrecognized option: t
$ busybox timeout -t 1 true >/dev/null 2>&1; echo rc=$?
rc=1
$ busybox timeout 3 sh -c 'true'; echo rc=$?
rc=0        (exact wrapper form used by the initd)
```

BusyBox 1.37 `timeout` usage is `timeout [-s SIG] [-k KILL_SECS] SECS PROG ARGS` — there is no `-t` option (that is the GNU coreutils form). This independently confirms Gwyn's round-4 finding (note #141).

## Findings

- **F1 (blocking) — every bounded step fails on Lynx.** `lynx-usb-gadget.initd:31,32,35,41,69,82` all use `timeout -t N`. On the real rootfs each one exits 1 ("unrecognized option: t"): mtu3 never loads, configfs never mounts, UDC never binds — the gadget silently never comes up. SSH is unharmed (correct), but the service provides nothing.
- **F2 (blocking) — validator is inverted (closes M3 in the wrong direction).** `lynx_usb_boot_persistence.py:79-80` now *requires* `timeout\s+-t\s+\d+`. A script with the correct BusyBox syntax (`timeout 5 modprobe mtu3`) fails with `missing_bounded_timeouts_in_start`; a script with the broken syntax passes. The check should be: accept bounded positional invocations and add a failing code `forbidden_timeout_dash_t` when `timeout -t` appears.
- **F3 (consequential) — tests pin the broken form.** `test_lynx_usb_boot_persistence.py:35,48,62,78,93,106` use `timeout -t 5` as the *valid* pattern; `test_missing_bounded_timeouts` (line 112) asserts on it. The suite is 32/32 green in a clean clone (verified) — but it is green because it asserts the wrong syntax.
- **F4 (accepted) — M1/M4 doc alignment.** Doc §3.1.4 now states failure is signaled (`return 1` / `eend $?`) and is non-fatal: no PID-1 halt, no runlevel abort, no SSH/Wi-Fi disruption. Correct and matches the script. Accepted.
- **F5 (accepted in intent, blocked by F1) — M2 configfs bounding.** Bounding the `mount -t configfs` step (initd:41) is the right call; re-do it with the positional syntax.

## Required fix spec for B9v2

1. `lynx-usb-gadget.initd`: all six sites → `/bin/busybox timeout 5 modprobe mtu3`, `/bin/busybox timeout 5 insmod "$MODULE_PATH"`, `/bin/busybox timeout 3 mount -t configfs none /sys/kernel/config`, `/bin/busybox timeout 3 sh -c "echo '$UDC_TARGET' > UDC"`, `/bin/busybox timeout 3 sh -c "echo '' > '$GADGET_DIR/UDC'"`. (Optionally `-k KILL_SECS` is available in 1.37; keep it simple.)
2. `lynx_usb_boot_persistence.py`: replace check #5 with (a) require at least one bounded positional invocation on the driver/UDC/mount lines, e.g. `timeout\s+\d+\s+(modprobe|insmod|sh|mount)\b`; (b) add `forbidden_timeout_dash_t` on any `timeout\s+-t\s` occurrence.
3. `test_lynx_usb_boot_persistence.py`: update fixture snippets to `timeout 5` / `timeout 3`; add `test_reject_timeout_dash_t` (script with `timeout -t 5 modprobe mtu3` must fail with `forbidden_timeout_dash_t`); keep `test_missing_bounded_timeouts` meaningful.
4. Design doc: reference snippet in §3 and §3.1.3 — use the positional form and cite the BusyBox 1.37 evidence (usage `timeout [-s SIG] [-k KILL_SECS] SECS PROG ARGS`).
5. Evidence: clean-clone usb suite green, and one live read-only check that the exact forms return 0 (already provided above).

Status remains **not installed** on Lynx; deployment is Aria's call.
