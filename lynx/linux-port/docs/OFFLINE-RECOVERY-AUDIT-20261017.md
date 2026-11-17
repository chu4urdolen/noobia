# Lynx offline recovery audit — 2026-10-17

This audit used saved files and receipts only. Lynx was not contacted; no
partition, slot, bootloader, recovery, or power state was changed.

The V19 trial image and August stock `boot.img` both exist at 64 MiB and pass
the fixed V19 trial tool's offline validation. Its freshly generated readiness
receipt is `logs/boot-a-wifi-v19-trial-1792251929363954739.json`. The receipt
records `phone_contacted: false`, no operations, and the exact bounded undo:

```sh
/noobia/lynx/tools/platform-tools/fastboot -s 89BYAY5L4T9HFUOV flash boot_a /noobia/lynx/linux-port/artifacts/stock-cph2493-August-eu-ota/boot.img
```

The stock image SHA-256 is
`a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995`; the
independent V19 checkpoint copy has the same hash. The tool pins the product,
slot, bootloader identity, stock baseline receipt, OTA integrity/signature
receipts, Fastboot binary, and image hashes before it permits a live operation.
It allows restoration while the thermal flash hold is active, but requires
fresh Fastboot identity and partition-size checks before issuing the write.
The matching stock `boot_a` write succeeded in a prior physical Fastboot
session, as recorded in `logs/boot-a-wifi-trial-1791753886161258334.json`.

This verifies that a concrete undo artifact and a previously successful undo
procedure are present. It does not verify the phone's current USB connection,
Fastboot mode, installed partition contents, or present hardware condition. The
latest known installed image remains V19 from the successful native Wi-Fi/SSH
trial. Do not call the phone restored to stock unless a later receipt proves
that write succeeded.

The thermal hold in `docs/SAFETY-HOLD.json` remains active. This audit does not
authorize or prepare a Linux write. V20's OpenRC handoff candidate remains
offline-only until the combined supervised hardware checks and thermal review
are complete.
