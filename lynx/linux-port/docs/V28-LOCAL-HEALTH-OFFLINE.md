# V28 local Wi-Fi, SSH and health candidate

Status: **one timed hardware trial proved autonomous Wi-Fi/SSH, but health
readiness was unconfirmed; V19 restoration pending**. Image:
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
After V19 restoration, the same health start and preflight scripts packed in
V28 ran on Lynx in RAM. Their on-phone SHA-256 values matched the V28 package,
and `/run/lynx/health-bootstrap/ready` was present. The live result is
`logs/autonomous-health-ram-trial-1792354806850319336/result.json`.
These tests do not prove V28's combined boot path on Lynx. Charging remains
untested. The general safety hold remains active; no V28 flash is authorized
by this build result.

The immediate recovery path remains the proven V19 `boot_a` image and matching
stock boot image. V28 should be trialed only after an exact-image observer,
passive USB timing, a fresh Fastboot preflight, and a scoped review of its
health failure paths. Preserve slot B and all recovery-related partitions.

The single guarded V28 write at `logs/v28-boot-a-trial-1792354942644784048.json`
passed exact Fastboot identity checks and changed only `boot_a`. The host did
not reboot Lynx. Passive USB timing is at `logs/v28-usb-1792354939283.json`;
the image-aware network observer is at
`logs/v28-diagnostic-observer-1792354939399135307/result.json`, with a
classification at `trial-summary.json` in the same directory. A valid beacon
arrived 118.234 seconds after Fastboot departure and pinned SSH verified the
V28 `/init` hash 118.490 seconds after departure. The on-phone log shows local
Wi-Fi readiness at uptime 95.63 seconds and autonomous health startup at
95.67 seconds. Battery monitoring read 25.8°C and 58% charge, and thermal
cooling setup was reached. The last authenticated probe completed before
the health-ready marker; the next probe failed and no further contact was
observed through 338 seconds after departure. The final health log was not
captured, so a clean power-off, reset, kernel fault, or radio loss cannot yet
be distinguished. Do not treat V28 as a healthy persistent boot or reuse its
consumed trial scope.
