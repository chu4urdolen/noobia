# Lynx portrait display control

The archive `~/Downloads/lynx_18_individual_poses.zip` contains 18 full-screen
1240×2772 RGB PNGs. `13_dance_180deg.png` is truncated and cannot be decoded;
it was excluded. The remaining 17 PNGs are in `/noobia/lynx/pics` with their
source hashes in `archive-manifest.json`. The source archive was left intact.

`tools/prepare_lynx_pics.py` converts the PNGs to little-endian RGB565 gzip
frames in `pics/frames`. The phone stores the compressed frames, about 11 MiB
total. The dance has 11 frames ordered 0°, 30°, 60°, 90°, 120°, 150°, 210°,
240°, 270°, 300°, 330° and plays each for 500 ms. The missing 180° frame is
skipped. The renderer reloads a frame for each presentation and flips between
two DMA-BUF framebuffers; it does not modeset for every image.

The portrait screen uses the pose as the background. It draws `LYNX`, a clock
when the system time is valid, and the live battery percentage in the quiet
space above the ears. It has no Alpine slogan. The verified touchscreen dims
the panel after ten seconds and wakes it on touch. The native preview rendered
on Lynx is saved at `/noobia/lynx/logs/portrait-preview.png`.

The renderer is the OpenRC `lynx-display` service. It reads an atomic
selection file under `/var/lib/lynx-display`, so selection does not require a
service restart. `/usr/local/bin/lynx-displayctl` validates commands locally.
Remote access uses Lynx's existing pinned Alpine SSH connection on port 2222;
no additional network port or listener is opened. Nexus convenience commands:

```sh
cd /noobia/lynx
python3 tools/lynx_display_remote.py list
python3 tools/lynx_display_remote.py status
python3 tools/lynx_display_remote.py pose 03_look_left
python3 tools/lynx_display_remote.py animate dance
python3 tools/lynx_display_remote.py pose 01_standing_smile
```

To add another 1240×2772 RGB PNG, convert it on Nexus and register its frame:

```sh
python3 tools/lynx_prepare_frame.py /path/new_pose.png --name new_pose
python3 tools/lynx_display_remote.py register new_pose pics/frames/new_pose.rgb565.gz
python3 tools/lynx_display_remote.py define-animation new_dance new_pose 01_standing_smile
python3 tools/lynx_display_remote.py animate new_dance
```

The CLI allows 2–64 registered poses per animation, with 500 ms per frame.
Only root currently controls the phone's display files. A future Lynx AI
service should get a dedicated account with scoped access rather than reuse
root SSH.

## Deployment state, 2026-10-27

The 17 compressed frames, control CLI, native portrait renderer, verified
display/touch modules, and OpenRC service are installed on Alpine. The service
is enabled in the default runlevel on the restored V50 boot image
`6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59`.
Its bootstrap checks that exact full `boot_a` hash before loading display or
touch modules. The V50 rollback file remains on Nexus. No boot partition was
modified for the portrait deployment.

A cold boot on 2026-10-27 reached Alpine and started all eight core services,
then OpenRC started `lynx-display` automatically. The first modeset reported
a CMDQ timeout and `lcm_prepare:...Successful`; the service retried once and
started the portrait renderer without another CMDQ error. The service reached
`[ started ]` at uptime 265 seconds, its PID was present, and
`lynx-status --assert-ready` passed. Rescue and Alpine reported the same boot
ID, `1a524657-04f4-4306-9458-c5ced1c2bfb0`. Remote `status` returned
`pose 01_standing_smile`; the full pose list and 500 ms dance were available.
The first boot attempt failed Wi-Fi contact and returned to Fastboot under the
V50 guard; one Fastboot reboot reached the successful boot without flashing.
Visual confirmation for this specific automatic boot was requested separately.

The first cold modeset timeout is still a driver problem to fix; the bounded
retry is a verified workaround. The host confirmation guard in V50 also means
Lynx is not yet fully independent of Nexus at boot. Prior watched hardware
trials confirmed portrait, touch wake, and dance animation on the V50 panel.

Offline checks passed: all 17 frames decoded on the phone, the renderer
created a full-screen preview, remote pose/dance switching worked, and frame
registration plus animation definition worked in an isolated filesystem.
