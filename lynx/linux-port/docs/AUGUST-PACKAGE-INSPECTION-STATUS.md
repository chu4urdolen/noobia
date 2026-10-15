# Rose's August CPH2493 package — access and inspection status

Update: a different manufacturer EU endpoint works. Its boot-chain images have
been extracted and checked, with a matching recorded LK build. The earlier
listing/CDN failures below are historical. See `AUGUST-RECOVERY-AND-LINUX.md`
and the live download/integrity reports for the current investigation.

Requested filename:
`CPH2493GDPR_11_13.1.0.561EX01_2023081414430000.zip`.

User-provided listings:

- https://romdevelopers.com/index.php?a=downloads&b=file&id=158830
- https://firmwaredrive.com/index.php?a=downloads&b=file&id=125242

The ROM Developers listing names the requested file and reports 6.42 GB.
Firmware Drive lists the repackaged service bundle name
`OnePlus_Nord_3_5G_CPH2493_MT6983_GDPR_11_13.1.0.561EX01_230814_MXML.zip`
and reports 6.43 GB. This is catalog information; it does not establish that
the archives are identical, genuine or compatible.

Both public download endpoints returned HTTP 403 on 2026-10-10.
`inspect_package_access.py` preserves the result in
`artifacts/august-package-access/access-report.json`. No credentials, purchase
or messages to site operators were attempted. The reason for the 403 response
was not established. No firmware bytes were obtained from these links.

Fifteen additional manufacturer CDN URL probes also returned 404, recorded in
`august-mirror-availability.json`; the earlier four probes are documented in
`FASTBOOT-RESTORATION-PLAN.md`. An unrelated OnePlus archive repository does
not list Nord 3 among its supported devices. A newer CPH2493 rollback package
was discovered but not substituted for this requested August package.

## Ready to inspect a local archive

Save the actual ZIP under `/noobia/lynx/downloads`. Inspection commands
below operate on host files only:

```sh
python3 /noobia/lynx/linux-port/inspect_local_stock_zip.py \
  /noobia/lynx/downloads/CPH2493GDPR_11_13.1.0.561EX01_2023081414430000.zip
```

The inspector computes the whole archive SHA-256, checks every ZIP member's
CRC, validates package model/platform metadata, extracts only bounded known
image/reference files to a new artifact directory, hashes them, and compares
LK build strings to Lynx's saved bootloader identifier. Packaged tools are
never executed. Existing output directories are preserved rather than replaced.
An OTA `payload.bin` package is deliberately rejected by this service-image
inspector and requires a separate extractor.

If the expected service images are present, the AVB auditor now accepts an
explicit directory, hash manifest and output report:

```sh
python3 /noobia/lynx/linux-port/audit_stock_avb.py \
  --stock-dir /noobia/lynx/linux-port/artifacts/stock-cph2493-August-service \
  --manifest /noobia/lynx/linux-port/artifacts/stock-cph2493-August-service/package-inspection.json \
  --report /noobia/lynx/linux-port/docs/august-stock-avb-audit.json
```

Its existing July-package behavior and report paths remain the defaults. Each
August component must subsequently be assessed for image format, DTB, recovery
init dependencies and module/kernel ABI. Signed image hashes and embedded keys
must be checked and compared with the retained July reference where applicable.
Self-computed SHA-256 and ZIP CRC alone do not prove publisher authenticity.
Embedded-key verification alone does not independently authenticate an OEM key.

## Present conclusion

Archive integrity: **not assessed; no archive obtained**.
Bootloader compatibility: **not established**.
Reliable recovery path: **not established**.
Phone partitions changed: **none**.

The exact native BusyBox kernel/initramfs already passed ARM emulation. This
stock package is sought as a recovery resource; restoring Android first is not
required, and native Linux remains the intended runtime.

## Direct manufacturer OTA retry

At the user's request, a full HTTPS GET of
`https://component-ota-afs.coloros.com/component-ota/23/08/14/4f1a650f088f4be39da1e6103015aa24.zip`
was attempted with wget at 2026-10-10 02:34:24 UTC. DNS and HTTPS connection
succeeded. The server returned HTTP 404 at 02:34:26 UTC, with a diagnostic
header containing `Document not found`; wget exited 8. This was a server
response, not a local USB or filesystem failure. No full ZIP was obtained.
The `.zip.part` path must not be treated as a usable image or firmware package.

The download log and machine-readable result are preserved in
`/noobia/lynx/downloads/august-ota-download.log` and
`/noobia/lynx/downloads/august-ota-download-result.json`.
Integrity, package contents, compatibility and restoration reliability remain
unverified for this OTA. Lynx was not contacted or flashed.
