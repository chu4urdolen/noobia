# V47 native compiler in an isolated data root

On 2026-10-23, Lynx boot ID `9054078d-aafa-4abf-9600-5c70f8234360`
installed an aarch64 Alpine toolchain under `/var/lib/lynx-devroot` on the
persistent ext4 data filesystem. The host system's `musl=1.2.6-r2` and
`musl-utils=1.2.6-r2` world constraints remained unchanged. The isolated
root has its own signed packages, including `musl-dev=1.2.6-r3`, GCC 15.2,
GNU Make 4.4.1, binutils, BusyBox, and `build-base`.

The root was created with its own APK database, copied Alpine public keys
and repository list, and `apk --root` with package scripts and commit hooks
disabled. A fresh-index simulation passed first. It contains no bind mounts
and no boot or recovery partition. The first install receipt is
`logs/v47-isolated-toolchain-1792787277369904188/result.json`. Installation
succeeded; that script's first verification failed only because it called
`head` through a BusyBox shell without a `head` symlink inside the small
root. The script has been corrected.

Independent pinned SSH verification then checked rescue `/init`, the exact
boot ID, host libc pins, all eight active services, available space, and
isolated package presence. GCC compiled a simple `<stdio.h>` program inside
the isolated root, and the resulting aarch64 binary ran there and printed
`LYNX_ISOLATED_NATIVE_BUILD_OK`. The passing receipt and raw output are in
`logs/v47-isolated-toolchain-proof-1792787366202318279/`.

After installation, the isolated root occupied 246 MiB and the host root
had 552 MiB free. Battery was 85% at 24.7°C and discharging at about
106 mA; no charging or thermal control was changed. No partition was
flashed. This proves local C compilation, not that Lynx can build the full
phone kernel within its current storage and power budget.

For a small build, place source inside `/var/lib/lynx-devroot/tmp/`, then
run `chroot /var/lib/lynx-devroot /usr/bin/gcc -o /tmp/program /tmp/program.c`.
Run it with `chroot /var/lib/lynx-devroot /tmp/program`. The separate
verification tool is
`python3 /noobia/lynx/tools/verify_v47_isolated_toolchain.py` from Nexus.
The installer is a one-time setup tool for an empty isolated root; do not
rerun it against the populated directory.

The isolated root is removable as a single data directory after stopping
any process using it. Removal has not been needed. V46 `boot_a` restoration
remains the existing Fastboot fallback; the toolchain is not part of boot.
