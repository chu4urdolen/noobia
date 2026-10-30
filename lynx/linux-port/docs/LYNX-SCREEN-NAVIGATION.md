# Lynx screen navigation

Requested 2026-10-29 after Noob confirmed the visible dance and chime.
Installed as a V50 Alpine display program update on 2026-10-29. No partition
was flashed. The original renderer and bootstrap are backed up on Lynx as
`/usr/local/bin/lynx-portrait-display.before-nav` and
`/usr/local/bin/lynx-display-bootstrap.before-nav`.

Keep Lynx's portrait as the home screen. Add two large touch buttons along
the bottom edge: **CONSOLE** and **STATUS**. A tap opens that page; tapping
its selected button again returns home. The buttons stay visible on every
page. The existing ten-second dim and touch-to-wake behavior stays in place.
A touch that wakes a dark screen should only wake it, so an accidental touch
cannot also change pages. Touch tracking must use the verified panel's raw
X/Y axes and act only on a completed single-finger tap inside a button.

The Console page initially shows only its title and an empty content area.
Do not invent a shell or grant local command execution as part of this UI.
Later console work can add a scoped, auditable interface separately.

The Status page should use current local readings and label their units and
freshness. Start with battery percentage, battery temperature, charging
state/current/voltage, SoC temperature, Wi-Fi address, SSH and Noob service
state, display/touch, sound and haptic readiness, and the registered motion,
compass, proximity, and light sensors. Values that fail validation or age out
must show **UNAVAILABLE** or **STALE**, never a plausible cached number.
GPS, Bluetooth, camera, and flashlight should explicitly show
**UNAVAILABLE** until their drivers and userspace paths are proven. The
ambient-light raw call currently returns no fresh event, so registration
alone must not be presented as a live lux reading.

The native candidate compiled with `-Wall -Wextra -Werror`. Full-size previews
are in `logs/nav-preview/home.png`, `console.png`, and `status.png`. The touch
parser passed a synthetic press, coordinate, and release test. The installer
`tools/install_v50_screen_navigation.py` checked the exact V50 boot and old
file hashes, backed up both old files, installed the new renderer with SHA-256
`3831ccb90d0d05e5377bfcb908e1c17777de6c4e60d56443dda28a781e4bd49d`,
updated the bootstrap hash pin, and restarted `lynx-display`. Receipt:
`logs/v50-screen-navigation-1793269553391682767/result.json`. The running
service, bootstrap file check, Alpine health, and NRP/1 `PING` all passed.
The display log shows the home portrait presented and the normal idle dim.
Noob confirmed the first live screen looked good. The display log recorded
`page=status`, `page=home`, `page=console`, `page=home` after physical taps;
both buttons and return-to-home therefore worked on Lynx.

The Status page was then expanded to show SSH, touch, and NRP service state,
and to list camera and flashlight separately. Its full-size preview is
`logs/nav-preview/status-v2.png`. Native compilation and the synthetic touch
parser test passed again. `tools/install_v50_screen_navigation.py` upgraded
the running renderer to SHA-256
`96a5b979e92d9903829162fa8b12266c624d03e7bd84ffe39fde382f639c1a0a`
and the matching bootstrap pin. The previous two-button version is backed
up as `.before-nav-status` beside both installed files; the original portrait
version remains in `.before-nav`. Receipt:
`logs/v50-screen-status-upgrade-1793271328779950201/result.json`. Display
service, bootstrap file check, Alpine health, and NRP/1 `PING` passed after
the upgrade. Noob's visual check of the expanded page is still pending.

The Console page was then connected to a local unprivileged shell and touch
keyboard, with separate output/error/warning colors. See
[LYNX-CONSOLE.md](LYNX-CONSOLE.md) for the service, privilege boundary, live
trial, and `.before-console` rollback files.

If navigation fails, stop `lynx-display`, restore both `.before-nav` files
to their original paths, and start the service again. The installer performs
that rollback automatically if the install/start step fails.
