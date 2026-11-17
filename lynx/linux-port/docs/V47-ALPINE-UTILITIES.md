# V47 Alpine utilities and native compiler hold

On 2026-10-23, pinned SSH on Lynx boot
`9054078d-aafa-4abf-9600-5c70f8234360` confirmed Alpine 3.24.2 on
ext4, a healthy battery sample, synchronized time, and all eight safety and
access services before changing userland. The rescue `/init` hash also
matched V47. Only `boot_a` contains V47; this work made no boot partition
write.

The first guarded attempt requested `build-base curl jq tmux rsync`.
`apk add --simulate` used an old package index and passed; the real
`apk add --no-cache` fetched the current index and stopped before installing
anything. Lynx pins `musl=1.2.6-r2` and `musl-utils=1.2.6-r2`, while the
fresh repository currently offers `musl-dev=1.2.6-r3`. That header package
requires the matching libc revision. The full attempt and stderr are in
`logs/v47-alpine-devkit-1792786958893748107/`.

The guarded utility-only pass installed `curl`, `jq`, `tmux`, and `rsync`
from the signed Alpine repositories. It used `apk add --no-cache --simulate`
first, then installed and verified each tool and all eight running services.
Afterward, the root filesystem had 797 MiB free and the exact libc pins
remained. The receipt and captured streams are in
`logs/v47-alpine-utils-1792787089608233197/`.

Native compiler installation in the active root is held until matching C headers are available or a
separate, rehearsed libc update has a restoration path. The current
[Alpine v3.24 aarch64 package index](https://dl-cdn.alpinelinux.org/alpine/v3.24/main/aarch64/)
lists `musl-dev=1.2.6-r3`; its public index no longer lists r2. Upgrading
the running libc solely to add a compiler would add risk to the live SSH
and recovery environment. The devkit script now uses a fresh-index dry run
so it will stop before an incompatible install.

The subsequent isolated native toolchain provides a working compiler in a
separate data root without changing these host libc pins. See
`V47-ISOLATED-NATIVE-TOOLCHAIN.md`.

Reproduce the completed utility verification with
`python3 /noobia/lynx/tools/install_v47_alpine_utils.py`. It checks the exact
V47 boot ID and rescue init; a later boot ID intentionally needs review
before the script is reused. The compiler attempt is preserved separately
as `/noobia/lynx/tools/install_v47_alpine_devkit.py`.
