# V28 local Wi-Fi, SSH and health candidate

Status: **offline built, not flashed**. Image:
`artifacts/local-health-v28-offline/nord3-local-health-untested.img`, SHA-256
`a22048376cec353af652c187da733eb198f1382efcf19924eebd5ba0b883d775`.

V28 derives from the exact V27a image that reached Wi-Fi and authenticated
SSH without a Nexus acknowledgement. It preserves the kernel, boot header,
all original supplemental members, and the proven Wi-Fi supervisor. The new
supplement adds only the reviewed health inputs, current health start script,
and local health handoff script. The changed `/init` starts an independent
300-second power-off timer, waits for local Wi-Fi/SSH, starts health monitoring,
then cancels the outer timer only after health reports ready. The health stage
has its own 180-second failure timer. The compressed supplement is 12,483,721
bytes, below the V19 loader's 40,000,000-byte bound.

The builder verifies exact parent and health-source hashes, shell syntax,
boot-image size and boundaries, kernel and header identity, and every CPIO
member after packing. Existing local health handoff and health-start fixtures
passed at `artifacts/autonomous-health-local-check-1792354399868756797/result.json`
and `artifacts/autonomous-health-start-check-1792354403985292644/result.json`.
These tests do not prove V28's combined boot path on Lynx. Charging remains
untested. The general safety hold remains active; no V28 flash is authorized
by this build result.

The immediate recovery path remains the proven V19 `boot_a` image and matching
stock boot image. V28 should be trialed only after an exact-image observer,
passive USB timing, a fresh Fastboot preflight, and a scoped review of its
health failure paths. Preserve slot B and all recovery-related partitions.
