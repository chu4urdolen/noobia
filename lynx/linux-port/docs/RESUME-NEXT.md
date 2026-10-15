# Paused for Noob's bedtime, 2026-10-12

Do not start hardware work until Noob resumes. No credentials needed currently.
All tools and files remain under /noobia/lynx.

CURRENT: matching August stock boot_a restored successfully without reboot.
Receipt: /noobia/lynx/logs/boot-a-wifi-trial-1791753886161258334.json.
Last observed phone mode Fastboot, USB001/008. Slot B and other partitions
untouched. Previous Wi-Fi image v3 is NOT currently installed. No phone trial
or Wi-Fi listener remains active; listener completed its bounded600s window.

First Wi-Fi trial returned to Fastboot about54s after reboot; zero beacons or
pinned SSH responses. Internal failed stage unknown; timing is only a clue.
Consolidated result and raw-file hashes:
docs/wifi-v3-first-hardware-result.json.
Read-only post-trial LK log: logs/pllk-1791753872288099107.*.
Reset NONRST_REG2=0x28002003, parsed status0x2, raw reset-origin label lk.

Concrete next fix: load exact stock reset-ti-syscon.ko before UFS. V3 omitted
it despite CONFIG_RESET_TI_SYSCON=m. Stock UFS module includes ti,syscon-reset;
published UFS probe explicitly creates a supplier device link and defers if
dormant. Reference saved docs/wifi-source-reference/ufs-mediatek.c. This is a
verified omitted prerequisite, NOT yet a proven cause of this trial failure.
Confirm stock DT supplier presence and module ABI before building next image.
Do not reflash unchanged v3 merely to repeat the same observation.

Noob requested a stable hex log readable after each experiment. Created:
linux-port/lynx-diag-stage.sh and tools/lynx_decode_stages.py. Records use
LXDG1 + session32 + sequence8 + uptime-seconds8 + stage4 + status4 + SHA256.
Numbers are hex; emission arguments are decimal. Checksums detect corruption,
not identity. Each producer owns a separate mode0600 RAM file:
/run/lynx/stages-{supervisor,bootstrap,wifi}.hex. Initialize each child once
with its own role before logging; ash background jobs inherit variables.
Copies go only to existing kmsg/pmsg character devices; no block device opens.
Logger NOT integrated into a phone image yet. Hardware persistence/retrieval
NOT established. Do not claim stable after-reboot handset logging works.

Real ARM64 BusyBox / exact stock kernel QEMU test passed nine checks:
artifacts/emulated-native-diag-stages-1791754278294064730/result.json.
Tool tools/test_native_diag_stages.py verifies emission, checksums/sequences,
permissions, invalid-input refusal, wrong sessions, corruption and truncation.
Decode a retrieved journal with tools/lynx_decode_stages.py CAPTURE --session
IMAGE_SESSION --output RESULT.json. Preserve full raw kernel/module logs too.

Read-only Fastboot readback probe FAILED cleanly: max-fetch-size empty;
standard client refuses fetch with Device does not support fetch command.
Saved tool tools/lynx_fastboot_readback_probe.py and raw receipt directory
logs/fastboot-readback-1791754078067214579/. No flash/erase/auth bypass.
Do not write partition logs without a verified retrieval route. SSH retrieval
is the next practical route once storage/bootstrap and Wi-Fi initialize.

Published log_store.c retained docs/wifi-source-reference/log_store.c. Its
userspace write handler only accepts boot-complete command0, not arbitrary
stage codes. No module load, PMIC/register marker modification or logging
partition write attempted.

Next authorized work after resume: integrate separate hex journals and the
reset supplier into a NEW candidate; preserve v3 and known minimal proof;
independently validate image/metadata/kernel/module ABI and tested control
flow; verify stock undo; then start a fresh pinned SSH listener before a
controlled boot_a-only trial. No physical timing request until ready.
