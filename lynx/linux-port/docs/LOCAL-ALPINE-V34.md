# V34 offline autonomous Alpine candidate

V34 is an **unflashed** `boot_a` candidate derived from the V33 image that
booted Alpine/OpenRC as PID 1. The stock kernel, command line, boot header
outside the ramdisk length, and all unrelated ramdisk members are unchanged.
The primary `/init` tail and verified supplementary payload change. The
image is private at
`linux-port/artifacts/local-persistent-alpine-v34-offline/nord3-local-persistent-alpine-v34-untested.img`,
SHA-256 `727d72621e69743d2939540e84ca137183dae0055e07df458da52bddc60d13d4`.

After the existing two-stage stock module bootstrap, the new tail starts
the proven Wi-Fi worker without waiting for Nexus acknowledgement. It keeps
an independent 300-second power-off timer while the phone has no health
supervisor. Once rescue SSH is ready, it places a one-boot local token and
starts the V31 health inputs and cooling retry entirely on the phone. The
health stage checks that no charger is online; native charging is still
unvalidated. It cancels the outer timer only after thermal, battery and
cooling supervision is live. It then invokes the V33 persistent Alpine
handoff with the guard's existing `local` authority, using the proven PID 1
standard-descriptor repair. A pre-exec handoff refusal leaves the monitored
BusyBox rescue environment up. A Wi-Fi or health startup failure requests
power-off rather than leaving an unmonitored phone running.

The earlier live V31 health trial and V33 PID 1 handoff establish the
individual stages, but their **autonomous combination is not yet proven on
Lynx**. The offline builder checked exact parent hashes and member scope;
the independent validator checked shell syntax, the V31 local cooling
fixture, exact stock kernel identity, payload hashes, and the pinned AOSP
AVB model. The model is not OnePlus LK. Receipts:
`linux-port/artifacts/local-persistent-alpine-v34-offline/build-result.json`
and `validation.json`.

`tools/lynx_v34_contact.py` polls pinned rescue SSH and captures boot,
health, network, mount and pstore diagnostics without sending an arm marker.
`tools/lynx_boot_a_v34_trial.py --prepare` verifies the exact image,
validation, pinned Fastboot binary, and **both** exact rollback images:
V33 `1d65456979d8a48d31de77c987b8aaf9b5ac11af62c51d00fdaff68ad47e747f`
and V19 `5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851`.
No write is implicit. A hardware trial requires Lynx cool, unplugged before
boot, a fresh Fastboot USB connection, collector already listening, and a
fresh identity/layout preflight. Flash **only `boot_a`**, then separately
reboot and remove USB promptly. Restore V33 or V19 through Fastboot if
boot/health/recovery behavior differs. Preserve slot B, bootloader and
recovery-related partitions.

The current installed `boot_a` remains V33. Do not describe V34 as booted,
safe for charging, or independent until a fresh hardware receipt proves it.
