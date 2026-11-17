# Lynx stock loader accepted; session authentication required

Second guarded stock-mode GPT probe:
`/noobia/lynx/tools/mtk-sessions/1791591655542090700`.

The user reconnected while holding both volume buttons and reported a dark
screen. Kernel USB events confirm 22d9:0006, OPLUS Preloader, at 03:22:24.
MTKClient reported successful device detection, regular/preloader mode, DA
stage 1 loading, and `Successfully booted to stage 2` with the archived loader.
The V6 loader was uploaded into RAM, not flashed to a storage partition.

The XML loader's session-authentication check returned true. Our checked_sla
guard then raised:

```
Loader requests session authentication; stop instead of trying fallback keys
```

The process exited with status 1. It did not proceed to printgpt, attempt a
fallback key, invoke security bypass, or write/erase a partition. No partition
table or device backup was obtained. The stock auth_sv5.auth file was not
sufficient to establish a usable readback session in this attempt.

This demonstrates that the supplied loader reaches its RAM execution stage on
Lynx. It does not demonstrate flash authorization or a verified restoration
path. Session authentication remains unresolved. A reset/power cycle discards
the RAM loader; reestablish physical Fastboot before any further experiment.

The minimal Linux image remains offline-validated, hardware-unproven and
ineligible for flashing under the agreed recovery requirement. Do not replace
the authentication guard with an automatic exploit or guess that a successfully
uploaded loader can read/write storage without authorization.
