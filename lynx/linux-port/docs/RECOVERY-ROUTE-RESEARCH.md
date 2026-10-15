# Recovery route investigation for Lynx

The native Linux objective remains unchanged. A recovery environment would be a
temporary diagnostic/restoration tool, not an Android or LineageOS installation.

## Device maintainer evidence

https://github.com/lineageos-on-vitamin/releases documents a Nord 3 recovery
installation through boot, dtbo and vendor_boot. Its current instructions require
Android 15 firmware 15.0.0.701(EX01) for CPH2491/CPH2493. The project was archived
June 4, 2025. Those recovery files cannot be assumed compatible with our July
2023 OxygenOS 13 reference package or Lynx's unknown installed firmware.

The documented route writes all three image types to both slots. It would
replace existing recovery resources and both boot paths; it is outside our
current preservation boundary. Do not execute those commands as a workaround.

## Current conclusion

We have not established a compatible diagnostic recovery image or complete
stock restoration procedure. The archived MT6983 package is a service bundle
with a scatter file, preloader and download-agent resources. A scatter file is
not a validated Fastboot restoration script. No service authorization or
download-agent compatibility has been demonstrated.

Next useful research is a recovery release explicitly targeting the older
firmware generation, or a documented CPH2493 stock restoration path that retains
bootloader access. Avoid both-slot writes and preloader/bootloader replacement.
Firmware downgrade/rollback compatibility must be established before treating
the old reference package as a known baseline.

No images were downloaded or flashed during this investigation. User action is
not currently required; repeating Fastboot queries will not resolve these gaps.
