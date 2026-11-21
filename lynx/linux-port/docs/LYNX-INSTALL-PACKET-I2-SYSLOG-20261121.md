# Install packet I-2: let Lynx keep sense lines (syslog level and size)

- **Author:** Gwyn.
- **Reviews:** Dushich second-reviews. Aria installs, in install session
  IS-2.
- **Status:** not installed.

## Why

Lynx's logger is started by `/etc/init.d/lynx-local-logs`, not by an OpenRC
`syslog` service. It runs `syslogd ... -s 512 -b 5 -l 4`.

BusyBox `syslogd -l N` logs **only messages more urgent than N**. This was
read from Lynx's own `busybox syslogd --help` on 2026-11-21:
- `-l 4` keeps emerg, alert, crit and err only, and **drops warnings and
  notices**;
- autonomy sense lines are logged at `user.notice` (5);
- **`-l 6` keeps notice and still drops info and debug.**

The display driver logs an `[ESD]check` kernel error about every 5 s, so
512 KiB files rotate in hours. v2 uses 2 MiB × 5. The root filesystem has
209 GB free.

## Precondition

Today's incident (forge lynx #226): Lynx's syslog was silent for 2 h
before an unexplained reboot. The logging stack is a suspect. **Install
only after Banshee's B38 investigation reports**, or with Aria's explicit
judgement that the two are unrelated.

## Files

| Repository | Phone | SHA-256 |
| --- | --- | --- |
| `lynx/tools/services/lynx-local-logs.initd.v1-installed`, the exact current file, fetched byte for byte on 2026-11-21 | `/etc/init.d/lynx-local-logs` | `1f3cf9510348703a6123cf38e5fe3dd8e689175543894cd11a58512fcaccdf3f` |
| `lynx/tools/services/lynx-local-logs.initd.v2` | `/etc/init.d/lynx-local-logs` | `dc19e3b5a5af550850969134a63c7cadddb12c25930c37952bc84fe9f160d2dc` |

The diff is one line, `-s 512 -b 5 -l 4` → `-s 2048 -b 5 -l 6`, plus a
three-line comment.

## Preflight (read-only)

```sh
lynx-board                                            # fresh, healthy
python3 lynx/tools/lynx_remote.py run "sha256sum /etc/init.d/lynx-local-logs; stat -c '%a %U' /etc/init.d/lynx-local-logs; rc-service lynx-local-logs status"
# expect the v1 hash above, root, and status ok
```

## Install

1. Copy v2 over `/etc/init.d/lynx-local-logs`, keeping the mode and owner
   recorded in the preflight.
2. Run `rc-service lynx-local-logs restart`.

The service's own `stop` removes its pidfiles, and `start` proves both
logger processes. Logging pauses for about a second during the restart.

## Warning: the restart cascades (found by Aria during IS-1a, forge lynx #296)

`rc-service lynx-local-logs restart` also restarts the OpenRC services that
depend on it: **display, haptic, audio and sensorhub**. During IS-1a this
left their start markers stranded until Aria repaired them. Plan for it:
1. Before the restart, note `rc-status` and that the portrait renderer is
   running.
2. After the restart, check each dependent service with
   `rc-service <name> status`.
3. If one is stuck, recover it the way Aria did: confirm the real process
   or renderer is alive first. Repair the marker if the process is healthy;
   otherwise run `rc-service <name> zap` then `rc-service <name> start`, one
   service at a time.
4. Finish with `lynx-status --assert-ready`.

Future logging packets should avoid restarting `lynx-local-logs`, or should
list the cascade in their own steps.

## Verify

```sh
python3 lynx/tools/lynx_remote.py run "rc-service lynx-local-logs status; ps -o args | grep '[s]yslogd'; busybox logger -t noobia-sense -p user.notice 'NOOBIA P0 autonomy install.test | I-2 check'; sleep 1; grep -c 'autonomy install.test' /var/log/lynx/messages; busybox logger -t noobia-sense -p user.info 'NOOBIA P0 autonomy info.test'; sleep 1; grep -c 'autonomy info.test' /var/log/lynx/messages"
```

Expect:
- status ok;
- the `syslogd` command line contains `-s 2048 -b 5 -l 6`;
- `install.test` counted at least once;
- `info.test` counted **0** (info is still dropped).

After 10 minutes, `ls -l /var/log/lynx/messages*` should show growth of
the same order as before. If it grows more than 10 times faster, roll
back.

**Record the baseline before installing.** During IS-1a the pre-install
rate was not measured, so the 10× check could not be evaluated (forge lynx
#302). Preflight must take two `ls -l /var/log/lynx/messages` readings five
minutes apart and record bytes per minute.

### What IS-1a showed (2026-11-21)

- Growth was 468 KB in 8 minutes, about 3.5 MB/h. That leaves about 3 h of
  history in 2 MiB × 5 files.
- In the last 2000 lines, 1908 were `kern.warn` and 92 `kern.notice`.
- Nearly all of them come from the UFS storage driver (`ufs_mediatek_mod`:
  `ufs_mtk_setup_ref_clk`, `ufs_mtk_boost_crypt`), about 7 lines/s. `-l 4`
  used to drop them.
- Hypothesis, not verified: a feedback loop, where each log write wakes the
  UFS reference clock and logs another warning.
- Follow-up: filter kernel warnings without losing `user.notice` sense
  lines. See forge lynx #306.

## Disable and rollback

Copy `v1-installed` back over `/etc/init.d/lynx-local-logs` and run
`rc-service lynx-local-logs restart`. Verify the `syslogd` command line
shows `-l 4` again. No other file changes.
