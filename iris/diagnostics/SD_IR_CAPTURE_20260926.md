# IR capture SD incident, 2026-09-26

- `/samples/ir_raw_73742.csv` passed Iris's immediate size/hash readback but
  later had its first 512 bytes replaced by the dictionary header and zeros.
  The rest of the file remained intact. The 52 observed pulses were copied to
  `thomson_tv_mute_73742.csv` before the board was powered down.
- The card was backed up under the Git-ignored
  `/noobia/iris/backups/IRIS-2026-09-26/`; `diff -qr` matched all original files.
- `fsck.fat -n -v /dev/sda1` reported no FAT allocation or directory errors.
- A two-file Linux write test in `/_noob_sd_probe_20260926` survived unmount and
  read-only remount. All original files still matched the backup. The probe
  directory remains on the card for now.
- Several older `ir_raw_*.csv` files are empty or zero-filled. Other sample
  CSVs and camera JPEG headers look intact. The evidence points to Iris's raw
  capture write path, but does not yet rule out board-side SD signalling or
  power trouble.
- Firmware now buffers raw capture writes in 512-byte blocks. The dictionary
  writer uses one checked write and fingerprints the capture before and after
  the dictionary update. The first `0.6.9-sdtest` check used the card absent;
  the subsequent card test is recorded below.

Do not call the incident fixed until a raw capture survives a dictionary write
and a power cycle.

## Follow-up

- `0.6.9-sdtest` mounted the card through SDMMC. Two new captures passed their
  immediate write/readback checks, but appending `SDTest,Mute,63093` to the
  dictionary changed the start of both new raw files. The new fingerprint guard
  caught it and returned an error. The dictionary append itself was present.
- A reversible SPI-backed build, `0.6.10-sdspi`, is now flashed. It uses the
  same card slot as CLK=42, MOSI/CMD=39, MISO/DAT0=41, CS/DAT3=38. It mounted
  and read an existing file. Two small `IR_SNAPSHOT` files were written, and
  the first file's header remained unchanged after the second write.
- Two raw captures under SPI (`ir_raw_105789.csv` and `ir_raw_107008.csv`)
  passed immediate readback. Both headers remained intact after appending
  `SDSPITest,Mute,107008` to the dictionary; the full-file fingerprint guard
  passed for the labeled capture. `IR_REPLAY 107008 1` parsed and transmitted
  the saved 155-pulse file successfully. After a power cycle, both headers and
  the dictionary entry remained intact and `IR_REPLAY 107008 1` succeeded again.
  SPI is the working Iris storage configuration; longer-term endurance is not
  yet measured.
- `0.6.11-sdspi` raised the common native-function registry limit from 96 to
  128. After flashing, `VM_LAST_STATUS` reported the 107-byte autorun program
  restored, and `VM_LIST_SAVED` listed 12 saved programs. IR replay and both raw
  capture headers still worked.
- Camera capture on `0.6.11-sdspi` failed because its still-photo path directly
  used `SD_MMC`, despite the mounted SPI backend. The common camera service now
  uses the storage service's filesystem for create/existence/remove as it
  already did for MJPEG. On `0.6.12-sdspi`, `CAPTURE` saved
  `/captured/cam_00000001.jpg` (16,339 bytes); readback found the JPEG SOI/JFIF
  header and `FFD9` end marker. Both raw-capture headers remained intact, and
  the 155-pulse IR replay still loaded.

IR replay reached Iris's own receiver in a five-burst loopback test, but the
saved Thomson TV Mute recording did not make the TV respond, including at close
range and with three repeats. Storage integrity and IR command validity are
separate questions; TV replay remains unverified.
