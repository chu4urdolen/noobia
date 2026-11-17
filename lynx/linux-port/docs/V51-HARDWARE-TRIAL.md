# V51 first hardware boot: failed before contact

On 2026-10-27, V51 image
`338f1280cbdc68e8896ff6b5ebb37fd79d0497280159ac35c962dd311f98847c`
was flashed to `boot_a` only after a matching Fastboot preflight. The pinned
serial, product, unlocked state, slot A, bootloader build, partition sizes,
and download limit matched. The exact V50 rollback image was checked before
the flash. Flash receipt:
`logs/v51-boot-a-trial-1793098022184374360/result.json`.

The guarded reboot receipt is
`logs/v51-boot-a-trial-1793098047243163201/result.json`. A pinned rescue
listener was active before reboot at
`logs/wifi-v19-contact-1793098035551583469/result.json`. Lynx left
Fastboot but produced **no rescue beacon or SSH within 600 seconds**.
Alpine SSH was also absent, and the phone did not return to Fastboot through
the rescue fallback. No display service was started. This establishes a V51
boot failure; it does not identify the failing initcall or prove which of the
three DSI instruction changes caused it.

The phone required physical Power + Volume Down to re-enter Fastboot. A
bounded watcher at
`logs/v51-auto-restore-watch-1793098399065105595/result.json` checked for
the pinned serial for 600 seconds. It expired without seeing Fastboot and made
**no restoration write**. Once Fastboot was available, the guarded
`tools/lynx_boot_a_v51_trial.py --restore-v50` restored the exact V50 image;
receipt: `logs/v51-boot-a-trial-1793099293836040326/result.json`.
The full `boot_a` hash was checked after restoration. Do not boot V51 again
without a revised candidate and a way to collect earlier boot diagnostics.

The portrait assets and controls remain on Alpine's persistent root. V50 is
restored and now starts the portrait service at boot. Its RAM-loaded display
path has a first cold modeset timeout; ESD recovery initializes the panel and
a second modeset succeeds. The automatic V50 boot check is recorded in
`docs/LYNX-PORTRAIT-CONTROL.md`.
