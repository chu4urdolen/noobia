Lynx payload read investigation
===============================

The original payload reader successfully reads, verifies and extracts the full
candidate in a stock-kernel ARM64 BusyBox VM using a real64MiB loop block device.
Receipt: artifacts/emulated-native-payload-loop-1792009523537673393/result.json.
The instrumented reader also passes real block I/O:
artifacts/emulated-native-payload-step-loop-1792009763482688016/result.json.
These use fixture partition metadata and do not establish physical UFS reads.

Physical bootstrap timing reports status154 after UFS guarded binding and boot_a
partition discovery. This identifies the own boot_a payload routine, not a
particular statement. Separate payload-step timing image is being tested.

Primary reference sources downloaded to docs/wifi-source-reference/:

- payload-genhd.c: block/genhd.c
- payload-partition-core.c: block/partitions/core.c
- payload-scsi-sd.c: drivers/scsi/sd.c

Repository: https://github.com/OnePlusOSS/android_kernel_5.10_oneplus_mt6983
Published Nord3 branch: oneplus/mt6983_t_13.1_oneplus_nord_3_5g
Pinned commit:81ec42ad5e803be0cba619f9f7bb298db7d33d7b
Raw URL prefix:
https://raw.githubusercontent.com/OnePlusOSS/android_kernel_5.10_oneplus_mt6983/81ec42ad5e803be0cba619f9f7bb298db7d33d7b/

This published source is not proven to match the exact stock g311738fbb5a8 binary.
The published SCSI disk source formats names with sd prefix and registers the
disk normally. Its operations do not supply a custom devnode callback in the
reviewed file. The block layer can delegate naming through disk->fops->devnode.
Partition code exposes volume labels through PARTNAME. These do not establish
Lynx's actual DEVNAME, node presence or partition uniqueness. No path change is
justified yet. Wait for the step-specific physical diagnostic.

Hypotheses remain candidate ambiguity, device-node absence, reported size/RO
ioctl failure, metadata failure, raw I/O failure, readback checksum mismatch,
or decompression/extraction failure under the physical memory environment.
Keep existing files/images and stock boot_a restoration ready. No partition
repair, calibration alteration, bootloader/recovery change, or radio test here.
