# LNX-86: include Wi-Fi credentials in Lynx's read-only security audit

Status: **candidate; no phone change yet**. Author/installer: Aria. Two Noobs
other than Aria review before installation; Noob authorizes the device change.
This changes only the existing on-demand audit script. No service restart,
Wi-Fi reconfiguration, credential read, or network change is involved.

| Nexus source | Lynx destination | SHA-256 | mode |
| --- | --- | --- | --- |
| `lynx/tools/security/lynx_config_audit.py` | `/usr/local/lib/noobia/security/lynx_config_audit.py` | `7f973d99d53dfb3e0ad04df32c8df5970bdde107cef22ebb6e1364ff5f1695ac` | 0644 root:root |

Preflight: Noob and Aria present, Lynx healthy, pinned SSH 22/2222 working.
Installed audit hash must be
`56484cac0dd7040c7e7e1bf291421a27662bf085c7ba05f2cf387e9ad4b582f1`,
and `/usr/local/lib/noobia/security/lynx_config_audit.py.pre-lnx86` must be
absent. Verify `/etc/lynx/wpa_supplicant.conf` is 0600 root:root and
`/etc/lynx` is 0700 root:root **with `stat`, not by printing its contents**.
Run the existing audit and expect exit 0. Offline tests:
`python3 -m unittest discover -s lynx/tools/security -p
'test_lynx_config_audit.py' -v` (6 pass).

Install from `/noobia` on Nexus using the pinned key and host alias:

```sh
lyssh() { ssh -p 2222 -o BatchMode=yes -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=yes -o GlobalKnownHostsFile=/dev/null \
  -o HostKeyAlias=lynx \
  -o UserKnownHostsFile=/noobia/lynx/secrets/lynx_known_hosts \
  -o ConnectTimeout=5 -i /noobia/lynx/secrets/nexus_lynx_ed25519 \
  root@192.168.100.107 "$@"; }
lyssh 'umask 077; cat > /tmp/lynx_config_audit.py.lnx86' < lynx/tools/security/lynx_config_audit.py
lyssh 'set -eu; test ! -e /usr/local/lib/noobia/security/lynx_config_audit.py.pre-lnx86; cp -p /usr/local/lib/noobia/security/lynx_config_audit.py /usr/local/lib/noobia/security/lynx_config_audit.py.pre-lnx86; install -m 644 /tmp/lynx_config_audit.py.lnx86 /usr/local/lib/noobia/security/lynx_config_audit.py; rm /tmp/lynx_config_audit.py.lnx86; sha256sum /usr/local/lib/noobia/security/lynx_config_audit.py /usr/local/lib/noobia/security/lynx_config_audit.py.pre-lnx86; python3 /usr/local/lib/noobia/security/lynx_config_audit.py --text'
```

Expected: new and backup hashes match the values above, and the audit reports
`OK` (no high finding). Verify the 0600 Wi-Fi credential mode again and run
`python3 lynx/tools/security/run_security_regression.py` on Nexus (15/15).

Disable/rollback: copy the exact backup back with `cp -p`, verify its original
hash, and run the old audit. This restores the previous behavior immediately;
no service or reboot is involved. Keep the backup for a later cleanup. If the
new audit fails, use the pinned SSH route to perform this rollback.

Reviews: pending, pending.
