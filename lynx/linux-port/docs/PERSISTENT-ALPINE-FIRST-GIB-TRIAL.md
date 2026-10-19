# Proposed persistent Alpine storage trial — prepared, not applied

The proposed target is **only bytes 0–1,073,741,823 of the `userdata`
partition** (`/dev/sdc85`, GPT name `userdata`). This is a destructive write:
the first 1 GiB currently contains unidentified, mostly incompressible data.
The rest of the 238.6 GB partition would remain byte-for-byte untouched by
the installer, but it has been sampled rather than fully backed up.

The entire first 1 GiB is saved on Nexus as eight 128 MiB gzip chunks at
`backups/userdata-chunks-1792414534852012623/`. Each chunk was decompressed,
checked for exact length, and compared with a fresh SHA-256 read from Lynx;
the first 16 MiB also match the earlier edge backup. The manifest state is
`verified-read-only-first-gib-backup`. The prior single-stream backup timed out
and is marked failed; it was not treated as complete. Read-only samples show
nonzero data through the first several hundred MiB and zeros at all sampled
locations from 1 GiB onward. Sampling does not establish that the unsampled
remainder is empty.

The host-only image at
`linux-port/artifacts/persistent-alpine-ext4-1792413794183987933/` contains
Alpine 3.24.2, signed OpenRC packages, Python, Git and Make in a 1 GiB ext4
filesystem. Its raw SHA-256 is
`c162ff3c14ae2c276514c0c485f5aa6bf9044810fb07135078df9c9cb1794dd0`;
the 57,579,838-byte transfer gzip has SHA-256
`d2088243f965fa24092256699d6b46fd7bc264edbbba042137ee725d7fa571ce`.
`e2fsck -fn` passed; the image mounted read-only on Nexus and also mounted
when presented as the first 1 GiB of a larger simulated block device. This
does not yet prove a handset mount.

`tools/install_persistent_alpine_userdata.py --prepare` passed on the live
V19 boot. Its receipt is
`logs/userdata-ext4-prepare-1792414996199859431/result.json`: pinned SSH,
unmounted `userdata`, healthy unplugged power state, and exact V19 `boot_a`
SHA-256 `5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851`.
The receipt is intentionally short-lived; rerun `--prepare` before an approved
write if more than 15 minutes pass or Lynx reboots.

If approved, the installer streams the compressed image through pinned SSH,
writes exactly 1 GiB starting at offset zero, synchronizes the block device,
reads the same 1 GiB back and checks its full SHA-256, then mounts `userdata`
read-only with journal replay disabled to check Alpine/OpenRC. It does not
flash `boot_a`, switch slots, alter GPT, or reboot. BusyBox V19 remains the
working rescue environment. A failed or interrupted write leaves V19 intact;
`tools/restore_userdata_first_gib.py` can write the eight verified original
chunks back and hash each against the phone. The rollback tool passed its
offline input audit, but no rollback write has been attempted.

This storage trial alone will not make Alpine start automatically. After a
successful on-phone read-only mount, the next work is a guarded BusyBox-to-
Alpine handoff and autonomous health/Wi-Fi/SSH boot candidate. V28's combined
boot loss remains unexplained, so do not reuse that image or replace V19 as
part of this storage trial. Native charging and unattended operation remain
unvalidated.
