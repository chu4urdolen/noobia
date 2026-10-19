# Persistent Alpine storage on Lynx — installed and verified

On 2026-10-19 Noob approved writing **only bytes 0–1,073,741,823 of the
`userdata` partition** (`/dev/sdc85`). Lynx was on the proven V19 BusyBox
boot, with pinned SSH at `192.168.100.4`, boot ID
`3990a1d8-963d-4d17-972e-b0b8a7b366e6`, an unmounted `userdata`, and a
ready health supervisor. The fresh preflight receipt is
`logs/userdata-ext4-prepare-1792420768175872179/result.json`.

The installer streamed a compressed Alpine 3.24.2 ext4 image through pinned
SSH and wrote exactly 1 GiB at offset zero in 38.8 seconds. It read all 1 GiB
back; Lynx's SHA-256 matched the source image:
`c162ff3c14ae2c276514c0c485f5aa6bf9044810fb07135078df9c9cb1794dd0`.
Lynx then mounted `userdata` as ext4 with `ro,noload`, checked Alpine release
3.24.2 and executable OpenRC init, and unmounted it. The result is
`logs/userdata-ext4-install-1792420775526722662/result.json` with captured
write and mount output. A later pinned SSH check confirmed the same boot ID,
ready health supervisor, and unmounted `userdata`. No boot image, slot,
bootloader, recovery partition, or GPT write occurred.

A follow-up read-only chroot check found that the checkpoint export omitted
`/dev`, `/proc` and `/sys` mount-point directories. On the same verified V19
boot, those three empty directories were created inside the ext4 root, then a
read-only remount confirmed them. Receipt:
`logs/persistent-alpine-mountpoints-1792420959866685595/result.json`. With
outer `/dev` temporarily bind-mounted into the read-only root, Alpine's
Python 3.14.8 and Git 2.54.0 both ran on Lynx; evidence is
`logs/persistent-alpine-chroot-1792420966768790818/result.json`. All mounts
were removed. The live filesystem now differs from the immutable source image;
its new full first-GiB SHA-256 is
`b2c328e21b4bbaf50f71835b5ed6bba0f59b85ccec8d28acdff48abba569d001`,
recorded at `logs/persistent-alpine-post-mountpoints-hash-1792420986027536356/result.json`.
The image builder now creates these mount points for future builds.

Before the write, the original first 1 GiB was saved on Nexus as eight 128 MiB
gzip chunks at `backups/userdata-chunks-1792414534852012623/`. Each chunk was
decompressed, checked for exact length, and compared with a fresh on-phone
SHA-256. The backup manifest is `verified-read-only-first-gib-backup`.
`tools/restore_userdata_first_gib.py` can write and verify those chunks if
rollback becomes necessary; its offline input audit and disposable file tests
passed. No rollback write was needed or attempted. The rest of `userdata` was
sampled, not fully backed up. The installer did not write beyond the first GiB.

The source image is under
`linux-port/artifacts/persistent-alpine-ext4-1792413794183987933/`; its
57,579,838-byte transfer gzip has SHA-256
`d2088243f965fa24092256699d6b46fd7bc264edbbba042137ee725d7fa571ce`.
It contains Alpine 3.24.2, signed OpenRC packages, Python, Git, and Make.
Host `e2fsck -fn`, read-only mount, and simulated larger-block-device mount
passed before the live write. The install and rollback stream commands also
passed a disposable 16 MiB fixture at
`linux-port/artifacts/userdata-stream-fixture-1792415146707277219/result.json`.
Both tools use `conv=notrunc,fsync` so a regular-file fixture preserves its
unwritten tail. Lynx's BusyBox accepted these exact `dd` flags in a RAM-only
check before the storage trial.

This proves a persistent Alpine filesystem on Lynx. BusyBox V19 is still PID 1;
Alpine does not auto-start. The next step is a guarded BusyBox-to-Alpine
handoff with health, Wi-Fi, and SSH maintained. V28's combined boot loss
remains unexplained; do not reuse that image or replace V19 merely because
storage is ready. Native charging and unattended operation remain unvalidated.
