# LNX-79 / LNX-87: reversible kernel network hardening trial

Status: **candidate, not installed**. Author/installer: Aria. Two Noobs other
than Aria must review, and Noob authorizes the attended phone change. This
runtime trial does not add a boot service, change routes, change SSH, touch
the modem, or reboot. It applies five sysctls, with exact original values
saved under `/run/lynx-sysctl-trial` (0700, root) and a Lynx-local 120-second
automatic restore unless explicitly confirmed from a fresh SSH session.

| Nexus source | Lynx destination | SHA-256 | mode |
| --- | --- | --- | --- |
| `lynx/tools/hardening/lynx_sysctl_trial.py` | `/usr/local/sbin/lynx-sysctl-trial` | `86e0c1e8094fa7d22aca75910b809073b67f5cef082411ce2dc7f5b09204bb46` | 0755 root:root |

## Policy and evidence

Read-only Lynx baseline (2026-11-25): `kptr_restrict=0`, `dmesg_restrict=0`,
`unprivileged_bpf_disabled=0`, `accept_redirects=1`, `rp_filter=0`. The trial
requests respectively `1`, `1`, **`2`**, `0`, `2`. BPF value `2` disables
unprivileged BPF but can be restored to `0`; value `1` cannot be cleared
until reboot, per the [kernel sysctl documentation](https://www.kernel.org/doc/html/v5.13/admin-guide/sysctl/kernel.html#unprivileged-bpf-disabled).
`rp_filter=2` is loose mode for her future Wi-Fi/cellular paths. The script
stops and restores original values if the kernel rejects any requested value.

## Preflight and install

Noob and Aria present; Lynx on stable power. Record wall time, boot ID,
battery/temperature, `lynx-status --assert-ready`, Wi-Fi address and default
route, NRP 4243, and both rescue SSH ports. Run the 15-check security
regression before and after. Confirm all five live sysctl values above;
`/usr/local/sbin/lynx-sysctl-trial` and `/run/lynx-sysctl-trial/snapshot.json`
must be absent. Stop on a mismatch. Run the offline tests before copying:
`python3 -m unittest discover -s lynx/tools/hardening -p 'test_*.py' -v`
(four tests pass).

From `/noobia` on Nexus, after review and approval:

```sh
lyssh() { ssh -p 2222 -o BatchMode=yes -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=yes -o GlobalKnownHostsFile=/dev/null \
  -o HostKeyAlias=lynx \
  -o UserKnownHostsFile=/noobia/lynx/secrets/lynx_known_hosts \
  -o ConnectTimeout=5 -i /noobia/lynx/secrets/nexus_lynx_ed25519 \
  root@192.168.100.107 "$@"; }
lyssh 'umask 077; cat > /tmp/lynx-sysctl-trial' < lynx/tools/hardening/lynx_sysctl_trial.py
lyssh 'set -eu; install -d -m 755 /usr/local/sbin; install -m 755 /tmp/lynx-sysctl-trial /usr/local/sbin/lynx-sysctl-trial; rm /tmp/lynx-sysctl-trial; sha256sum /usr/local/sbin/lynx-sysctl-trial; /usr/local/sbin/lynx-sysctl-trial enable; /usr/local/sbin/lynx-sysctl-trial status'
```

Expected hash matches the table; `enable` prints `pending; auto-rollback in
120s`; `status` prints `pending`. A second SSH session must verify all five
values, the same Wi-Fi address and default route, signed NRP STATUS, and both
SSH ports. Only then run `/usr/local/sbin/lynx-sysctl-trial confirm` from
that second session within 120 seconds; expected `active until disable or
reboot`. Re-run the 15-check security regression and record values.

## Disable and rollback

`/usr/local/sbin/lynx-sysctl-trial disable` restores the saved exact values
and prints `original values restored`; this is the disable switch. If SSH
is lost before confirmation, wait at least 120 seconds for the local timer,
then reconnect and verify all original values. The timer is a detached
process with no inherited SSH handles. It never reboots or powers off Lynx.
The trial is runtime-only; no boot sysctl service or configuration file is
added. If confirmation was given and a later problem appears, use the local
console or SSH to disable. Keep the installed script for inspection until a
separate reviewed cleanup.

Reviews: pending, pending.
