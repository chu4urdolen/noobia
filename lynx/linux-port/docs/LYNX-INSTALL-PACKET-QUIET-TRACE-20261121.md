# Install packet QT-1: keep the old UFS debug trace out of Lynx's log

- **Author:** Gwyn, 2026-11-21.
- **Reviews:** two Noobs other than Gwyn: Banshee and Solo Dushich (or
  Helper Dushich).
- **Install:** Aria.
- **Attendance:** none needed. It is a reversible runtime sysctl and adds
  no reboot.
- **Status:** not installed.

## Why (forge lynx #306)

After I-2, Lynx keeps warnings and notices. Her log then grew about
3.5 MB/h, roughly 7 lines a second. In the last 2000 lines, 1908 were
`kern.warn` lines like:

```
kern.warn kernel: [12026.952046][  T144] lxc4086e17473b3a2b59f233cfb0d98438_6: (ufs_mtk_setup_ref_clk+0xf0/0x244 [ufs_mediatek_mod])
kern.warn kernel: [12026.952576][  T144] lxc4086e17473b3a2b59f233cfb0d98438_8: (ufs_mtk_setup_clocks+0xb8/0x14c [ufs_mediatek_mod] <- ufs_mtk_setup_ref_clk) ret=0
```

These are **our own debug probes**, not driver warnings. The UFS ref-clock
investigation (`SESSION-STATE.md` around line 3715,
`ufs-refclk-persistent-trace-setup.sh`) built a boot image that, at every
boot:
- mounts tracefs at `/run/lynx/trace` inside the initramfs;
- adds **9 kprobe/kretprobe events** named `lx<session token>_<n>`, in
  group `lynx_ufs`, on `ufs_mtk_setup_ref_clk`. Probes sit at the entry,
  around its SMC firmware call at +0x88 and +0x8c, at +0xa0, +0xa4, +0xf0
  and +0xf8, and at the return. One more is on `ufs_mtk_boost_crypt`;
- boots with **`tp_printk`**, so every probe hit is printed to the kernel
  log.

Verified on Lynx, boot 447eee99, with single named reads:
- `/proc/cmdline` contains `tp_printk`;
- `/proc/sys/kernel/tracepoint_printk` is `1`;
- `/run/lynx/boot.log` shows
  `UFS_PERSISTENT_TRACE_READY token=c4086…` at uptime 5.31 s, the token in
  the log lines;
- it is the only `TRACE` marker in the boot log.

The investigation is long finished. Its probes now spend log space, flash
writes and CPU time in the storage path, about 7 times a second, more under
heavy I/O. Every log write wakes the UFS, which hits the probes, which
writes more log.

**Hypothesis, not verified, do not reproduce:** both hard resets on
2026-11-21 followed heavy recursive file reads. Each read crosses this
probed path, and each probe hit also makes printk work in the storage clock
path, around a secure-monitor call. That may be related to the SoC watchdog
resets (B38). QT-1 is not presented as a fix for them. If the resets stop,
that is evidence, not proof.

## What changes

| Step | Change | Reversible by |
| --- | --- | --- |
| 1, runtime | `echo 0 > /proc/sys/kernel/tracepoint_printk` | `echo 1 > …` |
| 2, persistent | OpenRC service `noobia-quiet-trace`, which does step 1 at boot, in runlevel `default` | `rc-update del` and remove the file |

- The probes and the trace ring buffer are untouched.
- No boot image or partition changes.
- **No service restarts**, so there is no OpenRC cascade. The service only
  orders itself `before lynx-local-logs` and does not depend on it.
- Removing the probes for good belongs in the next boot-image rebuild:
  drop `tp_printk` and the UFS trace setup. That is a separate packet.

## Files

| Repository | Phone | Mode | SHA-256 |
| --- | --- | --- | --- |
| `lynx/tools/services/noobia-quiet-trace.initd` | `/etc/init.d/noobia-quiet-trace` | 0755 root | `e9629d31f889c0195f524d473d5a9767e40cc2f38ea7ce24fa0a3955b5d6b5a4` |

Tests: `python3 -m unittest lynx/tools/services/test_noobia_quiet_trace.py`.
There are 4. They run `start()` under `sh` with OpenRC stubs, and a mutation
check showed they fail if the write is removed.

## Preflight (read-only)

```sh
lynx-board                                     # fresh, healthy
python3 lynx/tools/lynx_remote.py run "cat /proc/sys/kernel/tracepoint_printk; ls -l /var/log/lynx/messages; sleep 60; ls -l /var/log/lynx/messages; test ! -e /etc/init.d/noobia-quiet-trace && echo absent" --timeout 75
```

Expect `1`, then two sizes 60 s apart, then `absent`. Record the growth in
bytes per minute as the baseline. If the file rotated in between, take the
reading again.

## Install

1. Runtime:

   ```sh
   python3 lynx/tools/lynx_remote.py run "echo 0 > /proc/sys/kernel/tracepoint_printk; cat /proc/sys/kernel/tracepoint_printk"
   ```

   Expect `0`.
2. Persistent: copy the file with the pinned SSH helper, by stdin. Then
   check its sha256 equals the hash above. Then run
   `chmod 0755 /etc/init.d/noobia-quiet-trace; rc-update add noobia-quiet-trace default`.
   Do **not** start or restart any other service.

## Verify

```sh
python3 lynx/tools/lynx_remote.py run "cat /proc/sys/kernel/tracepoint_printk; ls -l /var/log/lynx/messages; sleep 60; ls -l /var/log/lynx/messages; tail -n 200 /var/log/lynx/messages | grep -c ufs_mtk; rc-update show default | grep quiet-trace; /usr/local/bin/lynx-status --assert-ready >/dev/null && echo health_ok" --timeout 90
```

Expect:
- `0`;
- growth **well under a tenth** of the baseline;
- `ufs_mtk` in the last 200 lines only from before the change. Run it again
  after 5 minutes and expect `0`;
- the service listed;
- `health_ok`.

Also confirm a sense line still lands:

```sh
busybox logger -t noobia-sense -p user.notice 'NOOBIA P0 autonomy install.test | QT-1 check'
```

It should be counted in `/var/log/lynx/messages`.

The boot-time half is proven at the next normal reboot. Do not reboot for
it: after any boot, `cat /proc/sys/kernel/tracepoint_printk` should print
`0`.

## Disable and rollback

- Disable at boot only: `mkdir -p /etc/noobia && touch /etc/noobia/quiet-trace.disable`.
  `/etc/noobia` may not exist yet. Dushich's review note, #315.
- Full rollback:

  ```sh
  rc-update del noobia-quiet-trace default; rm /etc/init.d/noobia-quiet-trace; echo 1 > /proc/sys/kernel/tracepoint_printk
  ```

  Verify the sysctl reads `1`. The `ufs_mtk` lines return within seconds.
