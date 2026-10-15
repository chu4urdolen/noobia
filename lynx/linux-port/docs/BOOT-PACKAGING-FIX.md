# Lynx: corrected boot packaging, 2026-10-10

The first authorized boot_a-only trial failed and the verified August stock
boot image was successfully written back. Lynx was left in Fastboot. The offline investigation below was followed by a separately authorized second
trial. It failed to show a stable Linux boot; stock boot_a was restored. See
`BOOT-A-LZ4-TRIAL-RESULT-20261010.md` for the final hardware result.

## Reproduced ramdisk defect

Both stock ramdisks use legacy LZ4; the failed native generic ramdisk used gzip.
Bootloader concatenation places the vendor ramdisk first, without padding.
[AOSP vendor-boot documentation](https://source.android.com/docs/core/architecture/partitions/vendor-boot-partitions)
requires matching compression formats. Generic files then overlay vendor files.

The earlier emulator proof used only our generic ramdisk and missed this handoff.
Combining the original gzip image with the real stock vendor ramdisk produces
`rootfs image is not initramfs (Decoding failed)` and a fatal PID 1 exit. Evidence:
`artifacts/emulated-mixed-ramdisks/{console.log,result.json}`.

The corrected legacy-LZ4 generic archive is byte-identical after decompression
to the first trial's archive. With the same stock kernel and vendor ramdisk,
it reaches `NORD3_NATIVE_LINUX_PID1_OK pid=1` and executes interactive shell
commands: PID 1 is `init`, architecture is `aarch64`, devtmpfs mounts are zero.
The isolated VM powers down after the checks. Evidence:
`artifacts/emulated-stock-vendor-lz4/{console.log,result.json}`.

This reproduces a packaging failure in the emulator; it does not establish
that this was the sole cause of the physical phone's loop.

## Boot-local AVB metadata

Stock vbmeta chains to boot's child vbmeta. The failed raw image omitted its
own footer. Depending on whether Fastboot retained the old partition tail,
this could yield invalid metadata or stale hash metadata; the actual tail
was not read back. The corrected image includes a boot hash descriptor and
footer at the end of the full 64 MiB partition, algorithm NONE, flags zero,
rollback index zero. It has no manufacturer signature.

The read-only host model uses actual upstream AOSP libavb. Stock returns OK.
The original image with a zeroed tail returns ERROR_INVALID_METADATA and loads
no boot partition. The corrected image returns ERROR_VERIFICATION for unsigned
metadata but loads boot under the unlocked allow-verification-error policy;
the locked-policy negative control rejects it. See
`docs/avb-boot-model-results.json`. This models upstream AVB, not OnePlus LK,
trusts the reference root key, and assumes stored rollback indexes are zero.
[AOSP AVB documentation](https://android.googlesource.com/platform/external/avb/+/refs/heads/main/README.md)
describes unlocked verification-error handling.

The independent image validator checks size, partition-end footer bounds,
boot hash coverage and digest, unchanged stock kernel, native init and static
BusyBox, initial console node, and 24 module version records.

## Second trial — executed, stock boot restored

Candidate: `artifacts/busybox-August-lz4-avb/nord3-busybox-candidate.img`

Size: 67,108,864 bytes. SHA-256:
`1990c30549bf41637ce4ab6dda28f0082ec74bcb1bd7fb8299913e1b555c41df`

Stock undo: `artifacts/stock-cph2493-August-eu-ota/boot.img`, same size. SHA-256:
`a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995`

`/noobia/lynx/tools/lynx_boot_a_lz4_trial.py` defaults to offline readiness.
Its checks passed, receipt:
`logs/boot-a-lz4-trial-1791604475489349173.json`.
It pins both images and Fastboot, checks the full OTA verification reports,
combined emulation and AVB model, and re-runs independent image validation.
Live actions additionally run fresh serial-bound identity/slot/size checks.
The earlier trial script remains pinned to the earlier artifact for history.

After authorization for a second trial, the prepared guarded entry point is:

```sh
python3 /noobia/lynx/tools/lynx_boot_a_lz4_trial.py --flash-linux --reboot
```

Its only flash command is:

```sh
/noobia/lynx/tools/platform-tools/fastboot -s 89BYAY5L4T9HFUOV flash boot_a /noobia/lynx/linux-port/artifacts/busybox-August-lz4-avb/nord3-busybox-candidate.img
```

If Linux fails, physically return to Fastboot and use the guarded undo:

```sh
python3 /noobia/lynx/tools/lynx_boot_a_lz4_trial.py --restore-stock
```

Exact undo command:

```sh
/noobia/lynx/tools/platform-tools/fastboot -s 89BYAY5L4T9HFUOV flash boot_a /noobia/lynx/linux-port/artifacts/stock-cph2493-August-eu-ota/boot.img
```

The undo leaves Lynx in Fastboot. No slot switch, erasure or other partition
write is part of this procedure. Stop if recovery behaves unexpectedly.
Stock boot_a Fastboot restoration already succeeded after the first trial;
stock recovery startup and byte-for-byte partition readback remain unproven.
The installed vendor_boot/DTBO/vbmeta were not read back. USB peripherals,
display and native Linux on physical MT6983 remain unproven. There is no SSH
server yet. Recovery entry may be affected by replacing generic init.

The commands above were executed only after explicit second-trial authorization.
Both the candidate write and stock undo succeeded; hardware Linux boot did not.
Do not treat this historical procedure as authorization for another trial.
