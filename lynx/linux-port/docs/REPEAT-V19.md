# Repeat the proven V19 boot

## Preserve these inputs

The local checkpoint is `/noobia/lynx/checkpoints/native-wifi-ssh-v19`, mode0700.
It contains the working boot image, matching stock boot image, build manifest,
and137 deduplicated input objects. Some objects contain credentials or OEM
components. Keep the entire checkpoint private; do not upload its images.

The public `known-good-v19/recipe.json` records every initramfs entry, order,
ownership, mode and content hash. Its runtime directory contains our exact
running text source. The reconstruction tool needs only this recipe, the
private object cache, stock boot and the small Python packer/codec modules.
Python3 and the host liblz4 shared library are required. Gzip/LZ4 output is
checked against the original hashes, so codec differences fail closed.

## Rebuild without touching the phone

From `/noobia/lynx`:

```sh
python3 tools/rebuild_known_good.py --output-dir linux-port/artifacts/rebuilt-v19-NEW
```

Choose a new output directory each time. The command refuses replacement and
requires byte-for-byte identity with the hardware-proven64MiB image:

```text
5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851
```

This already passed locally. It bypasses the long chain of V1–V19 image
mutations and has no USB or network operations. The output contains the same
private configuration as the checkpoint and must stay private.

A fresh GitHub clone cannot manufacture the private objects. Copy the protected
checkpoint through an authorized private channel, or reconstruct each matching
input from its original source and verify its recipe hash. No new download,
replacement kernel, signing-key change or credential regeneration is part of
an exact repeat. Changing inputs creates a new candidate requiring validation.

## Reconnect to the running phone

```sh
bash tools/lynx-ssh 'uname -r; cat /proc/uptime'
python3 tools/capture_lynx_live.py
```

Current lease is192.168.100.9. The helper pins the saved host key and uses the
dedicated client key. The collector is the authoritative way to discover a
changed DHCP lease.

## Boot again without reflashing

The installed boot_a is already V19. First start the collector on Nexus:

```sh
python3 tools/lynx_wifi_v19_contact.py --listen --seconds 660
```

Wait for `LISTENER READY`. Then a deliberate phone reboot may proceed from a
second terminal. No new flash is required. The collector authenticates the
current boot and writes its token acknowledgement into RAM, cancelling the
automatic fallback. The acknowledgement does not survive reboot. The first
success arrived about109s after listener startup; allow initialization time.

## If a controlled reflash is actually needed

Keep all existing local validation receipts and the verified matching stock
foundation. With Lynx in Fastboot, use the synchronized launcher:

```sh
python3 tools/run_wifi_v19_trial.py
```

It verifies the exact candidate and stock undo, checks live identity/layout,
starts the listener, flashes only boot_a and reboots once. It preserves raw
host observations and timing. The historical trial wrappers depend on local
firmware/validation receipts intentionally omitted from the public repository;
they are not unattended installers for arbitrary Nord3 handsets.

On success, leave native Linux running and save its logs. On failure returning
to Fastboot, inspect the receipt, capture the read-only bootloader log with
`python3 tools/lynx_pllk_log.py --connect`, then use:

```sh
python3 tools/lynx_boot_a_wifi_v19_trial.py --restore-stock
```

Never infer that a black screen alone is a failure or a successful kernel boot.
Stop if recovery or identity behaves unexpectedly. Do not erase, relock,
switch slots, or replace bootloader/recovery/calibration partitions.

## Diagnostic tools worth keeping close

| Tool | Purpose |
| --- | --- |
| `capture_lynx_live.py` | Verify native identity and archive bounded RAM diagnostics over SSH |
| `lynx_decode_stages.py` | Decode checksummed binary/hex stage journals offline |
| `lynx_experiment_index.py` | Rebuild the local experiment and last-write index |
| `lynx_wifi_v19_contact.py` | Public UDP discovery followed by pinned SSH proof and fallback cancellation |
| `lynx_trial_observer.py` | Passive timestamped USB observations |
| `lynx_fastboot_preflight.py` | Read-only device, slot and partition checks |
| `lynx_pllk_log.py` | Preserve raw supported bootloader log output and reconstruction |
| `test_wpa_control_pair.py` | Exact WPA binaries and launcher under stock ARM kernel, isolated VM |
| `test_native_vendor_wifi_v19_loop.py` | Exact payload extraction through a read-only block fixture |
| `validate_wifi_v19_image.py` | Independent candidate delta and safeguard verification |

VM tests establish software behavior, not physical device support. The actual
milestone proof is pinned hardware SSH plus live WPA state and captured logs.
