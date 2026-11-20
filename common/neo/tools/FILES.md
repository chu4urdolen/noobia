# Iris files and audio

Neo stores downloads by case-insensitive extension:

| Directory | Types |
| --- | --- |
| `/img` | jpg, jpeg, png, gif, bmp, webp, mjpeg, mp4 |
| `/vm` | nvm, bin |
| `/audio` | wav, mp3, flac, ogg, opus, aac, m4a |
| `/esp` | other files; also `.job.log` for transfer/playback results |

Paths, limits, USB address, and ALSA device are configured in
`/etc/noobia/noob-files.conf`; the example is beside this document.
The source SD file is never deleted. Existing destination files are never
overwritten. Downloads use a temporary file, verify byte count, then commit.
Extension routing is classification, not content validation.

## BLE / ESP natives

```text
CALL_MIXED NEO_FILE_DOWNLOAD "/captured/capture-00000001.jpg"
CALL NEO_FILE_STATUS
CALL_MIXED VM_DOWNLOAD 0 "example.nvm"
CALL_MIXED AUDIO_PLAY "recording.wav"
```

The CALL_MIXED form above has no numeric arguments except VM_DOWNLOAD.
The local wrappers are `irisctl neo-download PATH`, `neo-file-status`,
`vm-download FILE.nvm [REPLACE]`, and `audio-play BASENAME`.

FILE_STATUS: `running=1` means in progress; after completion `exit=0` means
success. `exit=-1` means no completed job. A second job is rejected as BUSY.
Downloads are asynchronous: the ESP must return to its command loop before
Neo can ask it for SD chunks, avoiding a recursive-call deadlock.

VM_DOWNLOAD reads a raw `.nvm` bytecode file from Neo's configured VM directory
in 128-byte chunks. Only VM files of 1..1024 bytes are accepted. It saves via
the common ESP program store as `/programs/prog_NAME.nvm`, with atomic backup
handling. REPLACE defaults to 0. It does not LOAD, RUN, stop, or replace the
active VM. Use existing VM_LOAD_SAVED and RUN commands explicitly afterward.
File size is checked; bytecode validity is checked by the VM when executed.
Source files must stay unchanged during a transfer.

## Neo local commands

```sh
noob-files fetch /captured/capture-00000001.jpg  # synchronous
noob-neoctl download /audio/recording.wav       # asynchronous service job
noob-neoctl file-status
noob-neoctl audio-play recording.wav
```

WAV playback uses `aplay` and the PCM5102A ALSA device. Compressed audio needs
optional `/usr/bin/ffplay`; it is not installed automatically. Only basenames
in the configured audio directory may be played, not arbitrary Linux paths.
No shell command strings are accepted over the bridge.

## Tests and deployment

`bash neo/tests/test-noob-files.sh` checks multi-chunk binary copying (including
NUL bytes), extension routing, collision refusal, and invalid paths using a
loopback fixture. No real ESP, sensors, or speakers are touched by this test.

2026-10-02: Neo tools/service and four directories installed; ESP combined
image built and flashed, flash hashes verified. Saved 107-byte detector VM
restored. Local transfer regression passed. Live SD -> Neo VM and WAV copies
passed; Neo -> ESP VM bytes matched exactly with the active VM unchanged.
BLE-triggered camera download saved 24,607 bytes to /img/cam_00000005.jpg
with worker exit=0. WAV saved 32,044 bytes to /audio/audio_35266.wav.
One-second WAV playback through PCM5102A completed with exit=0; audible
output needs user confirmation (the test cannot establish speaker wiring).
