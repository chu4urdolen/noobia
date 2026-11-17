# Native software-reboot evidence — 2026-10-10

The controlled test produced an automatic Fastboot return with the exact reboot-mode signature requested by the native Linux init. This is strong hardware evidence that native userspace executed, not a working USB/Linux installation or a captured native console marker.

Confidence clarification: native PID1 execution is strongly supported but not
conclusively proved. The actual command was normal `fastboot reboot`, not
`reboot bootloader`; no buttons were reported, and mode3/software-reset0x2
matched the native init's intended request. However, no physical native text
was captured, exact return timing was missed, and the full proprietary
bootloader fallback/reset graph has not been excluded. Earlier conversational
wording claiming definite execution was too strong. Treat the result as
indirect evidence and seek a timed repeat with a matching no-reboot control
or a direct native output marker before declaring a confirmed hardware boot.

Prepared image: artifacts/busybox-August-boot-proof-bound-guards/nord3-busybox-candidate.img, SHA256 a9a72334185a5ddec9b6e3ece6e9e01600582f62c4db7bebc8ce87c4d5c3fe43. Exact August stock kernel; native BusyBox PID1; matching mtk_wdt, reboot-mode and syscon-reboot-mode drivers; one freestanding ARM64 RESTART2 bootloader request only after actual driver/node/property checks. It does not start the USB gadget stack or write partitions. Preliminary artifact busybox-August-boot-proof is retained separately.

The ARM64 helper executed under the exact stock kernel in QEMU and the kernel printed Restarting system with command bootloader, exiting QEMU successfully: artifacts/emulated-reboot-helper-1791662465537639804/result.json. The exact full image plus vendor-before-generic ramdisk refused the reboot on virtual hardware and remained PID1: artifacts/emulated-boot-proof-guard-1791662599378418727/result.json. Eleven exact-source host guard cases passed: tools/test-artifacts/boot-proof-guard-1791662566283189527/result.json. An initial fixture path substitution also changed the driver name; this test-only bug was fixed, and the failed artifacts were retained. Independent image and AOSP unlocked/locked AVB checks passed: docs/boot-proof-validation.json. AOSP AVB is not OnePlus LK.

User's existing boot_a-only native-trial authorization applied. Stock undo hash, matching baseline and exact restore command were checked before flashing. Trial accepted only boot_a and one reboot: logs/boot-a-boot-proof-trial-1791662841074803432.json. No other partition, slot or bootloader change. User was told to leave buttons untouched. USB changed from original Fastboot001/021 to absent, then returned as new Fastboot001/022. The first observer expired shortly after reboot; the second found Fastboot, so exact return latency was not captured.

Pre-trial log: logs/pllk-1791661502886412997.clean.txt. NONRST_REG2=0x20000000, low mode bits0; ramconsole watchdog status0. Post-trial log: logs/pllk-1791662950347665197.clean.txt. NONRST_REG2=0x28002003, low mode bits3; ramconsole watchdog status0x2; long-pressed reboot0; LK boot mode99. Mode3 matches the actual stock FDT mode-bootloader property. The log's raw rst-from-lk label remains and is preserved; this minimal init omitted OEM boot-stage-reporting modules. No physical native console text was retrieved. Hardware interpretation remains explicitly indirect. Consolidated evidence and limitations: docs/boot-proof-hardware-result.json.

After saving reset evidence, verified stock boot_a undo succeeded with no reboot: logs/boot-a-boot-proof-trial-1791662962729666883.json. Last persistent boot_a is stock; Lynx is in Fastboot, with no observer/probe running. Native proof image is preserved locally. USB serial/networking and a usable native OS are still unproved.

The earlier serial-verification warning was inspected in stock LK. The mismatch path returns an error and the caller logs then joins its normal continuation. No halt or forced Fastboot was found on that local failure path; no device identity data changed. Stock boot.img has a1650580-byte generic ramdisk, and the saved Nord3 board configuration does not declare separate init_boot use. Its partition's existence alone was not evidence that boot_a was the wrong trial target.

Next focused investigation: compare native USB/module bringup with this three-driver baseline. The candidate no longer needs to be judged only by USB enumeration: the standard software-return proof provides another observable result. Keep the original USB image, all proofs and stock restore intact. No additional trial is currently running.


## Follow-up reset-handler review and pending experimental detail

The ordinary `reboot` literal is suffix-merged into another string, explaining the first failed pointer lookup. Actual registration references locate normal reboot handler at analysis0x106cb4 and reboot-bootloader handler0x106ce0. The normal handler acknowledges then calls platform reset with1,1; it has no explicit mode3 setter. The bootloader handler explicitly passes3 to its mode setter then resets with1,7. Evidence: docs/lk-reboot-string-references.json and lk-fastboot-reboot-handlers.disassembly.txt. This strengthens the controlled native-init interpretation; complete proprietary reset graph remains unproved.

Asked the user whether any buttons were pressed after the no-buttons instruction and before Fastboot return; reply pending. This is an experimental observation check, not a new permission request. Do not equate a bareOK popup-continuation reply with a button-state confirmation. Current phone remains stock boot_a in Fastboot, node001/022; no trial or observer runs. Preserve proof artifacts and prepare USB/module comparison only after accounting for this control detail.


## Human observation confirmed; BusyBox first

Noob explicitly confirmed that no buttons were touched and Lynx was in Fastboot after the trial. This closes the pending experimental-control question and strengthens the native-init software-reboot proof. On the next turn Noob requested that the result be documented and coding continue, then clarified BusyBox first. Current development milestone is a live BusyBox USB shell using the already compatible stock kernel; kernel rebuilding and distribution integration follow specific demonstrated needs. No new flash is authorized by mere build-tool output; existing scoped controlled-trial authorization and restoration checks continue to govern any trial.
