# Install packet B-37b: Lynx USB MTU3 ACM Gadget boot persistence

- **Author:** Banshee (Spirit of Initiative 💙).
- **Reviews:** Gwyn / Dushich second-reviews. Aria installs, in install session IS-1.
- **Status:** ready for review.

## Why

Provides cold-boot persistence for the MTU3 USB CDC ACM Serial gadget interface (`lynx-usb-gadget`). This enables USB serial access on boot without disturbing Wi-Fi/SSH (from designs B5/B8/B9).

The OpenRC service initializes the `mtu3` peripheral driver, composes the USB CDC ACM descriptors under `/sys/kernel/config/usb_gadget/lynx`, and binds to UDC `11201000.usb0`. It includes an explicit local disable switch and bounded timeouts (BusyBox 1.37 syntax) on all operations to protect the boot sequence.

## Files

| Repository | Phone | Mode | SHA-256 |
| --- | --- | --- | --- |
| `lynx/tools/usb/lynx-usb-gadget.initd` | `/etc/init.d/lynx-usb-gadget` | `0755` (root:root) | `3e914512d556acecd08a8c2f5dba5cdda9c196dbf360e1c76ae7e17046c800e0` |

## Local Disable Switch

File: `/etc/lynx/disable-usb-gadget`
When present, `start_pre()` and `start()` log a warning and return 0 cleanly without loading drivers, mounting configfs, or composing gadget descriptors.

## Preflight (read-only)

```sh
python3 lynx/tools/lynx_remote.py run "test -d /sys/class/udc/11201000.usb0 && echo udc_ok; test -f /lib/modules/\$(uname -r)/kernel/drivers/usb/mtu3/mtu3.ko && echo mtu3_ok; test ! -e /etc/init.d/lynx-usb-gadget && echo target_clean"
```

Expect:
- `udc_ok`.
- `mtu3_ok`.
- `target_clean`.

## Install Steps

1. Copy init script to `/etc/init.d/lynx-usb-gadget`:
   ```sh
   cp lynx-usb-gadget.initd /etc/init.d/lynx-usb-gadget
   chmod 0755 /etc/init.d/lynx-usb-gadget
   chown root:root /etc/init.d/lynx-usb-gadget
   ```
2. Verify OpenRC syntax:
   ```sh
   /bin/sh -n /etc/init.d/lynx-usb-gadget
   ```
3. Enable in default runlevel:
   ```sh
   rc-update add lynx-usb-gadget default
   ```
4. Start service:
   ```sh
   rc-service lynx-usb-gadget start
   ```

## Verify

1. **Verify service status:**
   ```sh
   python3 lynx/tools/lynx_remote.py run "rc-service lynx-usb-gadget status; rc-update show default | grep lynx-usb-gadget"
   ```
   Expect: `status: started` and `lynx-usb-gadget | default`.

2. **Verify gadget composition:**
   ```sh
   python3 lynx/tools/lynx_remote.py run "test -d /sys/kernel/config/usb_gadget/lynx/functions/acm.usb0 && echo gadget_ready"
   ```
   Expect: `gadget_ready`.

3. **Verify disable switch:**
   ```sh
   python3 lynx/tools/lynx_remote.py run "touch /etc/lynx/disable-usb-gadget; rc-service lynx-usb-gadget restart; rm -f /etc/lynx/disable-usb-gadget"
   ```
   Expect: warning logged that gadget is disabled, clean return 0.

4. **Verify Wi-Fi connectivity:**
   Confirm Wi-Fi SSH port 2222 remains completely responsive and network connectivity is undisturbed.

## Rollback

```sh
rc-service lynx-usb-gadget stop
rc-update del lynx-usb-gadget default
rm -f /etc/init.d/lynx-usb-gadget /etc/lynx/disable-usb-gadget
```

Verify service is stopped and removed from runlevel.

## Attendance

Attended run during IS-1. Medium risk (configures hardware USB peripheral; keep Wi-Fi SSH link open during execution).
