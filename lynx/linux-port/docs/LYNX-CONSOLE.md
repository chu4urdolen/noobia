# Lynx local console

Implemented 2026-10-29 on the V50 Alpine system. The Console button opens a
readable shell output pane, a visible STDIN field, and a touch keyboard.
The keyboard has **ABC** and **SYM** modes. Together with case toggle, they
cover all 95 printable ASCII characters, including `~` and `\\`. The bottom
row provides case toggle, mode toggle, space, backspace, and Enter. Two teal
horizontal scroll bars sit below the output and STDIN areas; a vertical bar
sits at the right edge of the output area. Tapping the
output bar moves its 45-character window across a line of up to 100
characters; tapping the input bar moves its 40-character window across a
command of up to 160 characters. Typing follows the end of the command. The normal
ten-second dim and touch-to-wake behavior remains. The first tap on a dark
screen wakes it without activating a key. The Console and Status buttons
still return to the home portrait when tapped a second time.

The local `lynx-console` OpenRC service starts a persistent `/bin/ash -i`
shell as a dedicated `lynx-console` user (UID 101 on the observed boot), with
no password login. It has a private home directory and no `sudo` privileges.
The display program remains root for DRM/touch hardware, but only sends
bounded printable ASCII commands over `/run/lynx-console/control.sock`.
The socket and its directory are local and private; no network listener was
added. Commands are limited to 160 characters.

The daemon reads stdout and stderr on separate pipes. Its bounded 64-line
snapshot lives in `/run/lynx-console/snapshot.txt` and is refreshed
atomically; raw console history is not persisted. Lines from stdout are white,
stderr is red, and lines beginning `warning:` or `warn:` are amber.
**STDWARN is a display category, not a POSIX file descriptor.** Typed commands
and shell prompts are teal. The shell has no controlling terminal yet, so
programs requiring TTY job control may refuse to run. This is a local shell
for basic commands, not a privileged maintenance console.
The shell prompt expands `${PWD}` each time, so it shows the current working
directory followed by `:`. It updates after `cd`; a live `cd /tmp` check
produced `/tmp:`.

Wisp's `/noobia/wisp/server.c` and `index.html` informed the persistent shell,
bounded replay, output area, and command field. Wisp merges output through a
PTY; Lynx uses separate pipes so stderr and warnings can be colored. Bee's
autocomplete source was not present in the local Noobia tree or Rose backup
paths inspected; AI completion is deferred until its source is located and
the input protocol is reviewed.

## Verification and recovery

The console daemon passed an isolated local integration test with distinct
stdout, stderr, and warning messages, command input, and clean shutdown.
`tools/install_v50_console_service.py` installed the unprivileged service;
the first attempt stopped because BusyBox created the account in `nogroup`
without a same-name group. The OpenRC service was corrected to use that
group. Successful receipt:
`logs/v50-console-service-1793275518819507642/result.json`.
On Lynx the daemon UID was 101; `pwd` returned `/var/lib/lynx-console` and
all three output categories appeared in the snapshot. The daemon script was
subsequently updated to classify the shell prompt as input and its no-TTY
notice as a warning; the previous script remains at
`/usr/local/bin/lynx-console.before-prompt-fix`.

The renderer compiled natively with `-Wall -Wextra -Werror`; both touch and
keyboard key self-checks passed. A full-size preview is at
`logs/console-preview/console-live.png`. The working prior Status renderer
and matching bootstrap are backed up as `.before-console` files beside the
installed files. The console-enabled renderer has SHA-256
`381dde317610f36c2289632d858d267e3b0773f853e3b863985ca6c2984fc93a`.
Install receipt: `logs/v50-screen-console-upgrade-1793275678044883893/result.json`.
Alpine health, display bootstrap, console service, and NRP/1 `PING` passed;
the V50 boot image hash remains
`6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59`.
No partition was flashed. Noob's visual and touch-input confirmation is
pending.

The complete keyboard, scroll bars, and current-directory prompt were then
installed as a display and daemon update. The console daemon SHA-256 is
`3da51157d7d411c3c67ad856e324f0c3d74b53810a320d8c6ef3f0843f05ce99`;
its previous script is backed up as `.before-cwd-prompt`. The native renderer
SHA-256 is
`3a23bdd1c988d535cd0b8609d90a0a2d4e9de5a6aec9450c54b94e4bdfae11db`;
the previous renderer and bootstrap are backed up as `.before-console-symbols`.
The symbol-key preview is `logs/console-preview/console-symbols.png`, and
`tools/install_v50_screen_navigation.py` recorded the upgrade in
`logs/v50-screen-console-symbols-1793276591999656826/result.json`.
Both touch and keyboard self-checks, native compilation with `-Werror`,
Alpine health, display and console service checks, and NRP/1 `PING` passed.
The boot image hash remained the same. Noob's physical key and scroll-bar
check is pending.

The final renderer corrects the scroll bar's far-right touch position, so
tapping its right edge reaches the last character. It has SHA-256
`2ce7523366c02e2578c5d97a93fc1ae02afa61d081a97975ce8009080ed344df`.
The installed renderer and bootstrap can be rolled back to the prior version
using their `.before-console-scroll-fix` copies. The install receipt is
`logs/v50-screen-console-scroll-fix-1793276740019114369/result.json`.
After installation, both services and Alpine health passed, the console
snapshot contained `/tmp:` and `/var/lib/lynx-console:` prompts and a long
output line, and `/dev/sdc39` still matched the V50 boot image hash above.
Noob confirmed that the horizontal scroll bar works on Lynx.

The next display update adds a vertical scroll bar at the right edge of the
console output. The console opens at the newest 14 lines; tapping higher on
the bar shows older lines from the daemon's bounded 64-line snapshot, and
tapping its bottom returns to the newest lines. The native renderer SHA-256 is
`656fa401e5d1c67fe94208d3d25a9af3761a3e513b92c19968662c3ecfb073f0`.
Its preview is `logs/console-preview/console-vertical.png`; the installer is
`tools/install_v50_console_vertical_scroll.py` and its successful receipt is
`logs/v50-screen-console-vertical-1793301930717998813/result.json`.
The previous renderer and bootstrap are backed up beside the installed files
as `.before-console-vertical`. This changed no boot partition. Noob confirmed
that the vertical scroll bar works on Lynx.

To return to the last working Status renderer if the console display fails,
stop `lynx-display`, copy the two `.before-console` backups to their original
paths, and start `lynx-display`. To disable the shell service:
`rc-service lynx-console stop; rc-update del lynx-console default`.
