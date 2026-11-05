# Aria's local device tools

## Two-pane Codex interface

Run `noobia-codex` in a terminal on Nexus. It opens a tmux session with Aria's
normal Codex chat on the left and a live, read-only Dushich activity monitor on
the right. The monitor automatically follows the newest handoff. It shows
status, recent commands, and final verification while Dushich works. When no
task is running it shows the last handoff as history, labeled accordingly. The raw
event stream remains available with `dushich-bridge events HANDOFF_ID`.
Use `noobia-codex --resume SESSION_ID` to put a saved Aria Codex conversation in
the left pane. This explicitly replaces the current left pane's CLI process;
omit it to keep an already running pane or start a fresh conversation.

Use `Ctrl-b` then an arrow key to switch panes, `Ctrl-b z` to zoom a pane, and
`Ctrl-b d` to detach without stopping the session. Run `noobia-codex` again to
reattach. The right pane is for observation; send tasks from Aria's left pane
through the `dushich` MCP tools. This is a terminal interface on Nexus, not a
split view inside the current ChatGPT page.

## Delegate coding to Dushich

Aria's default Codex CLI has a local `dushich` MCP server with `dushich_start`,
`dushich_status`, `dushich_wait`, and `dushich_report` tools. `dushich_start`
returns an ID immediately. Dushich works quietly in his own workspace; the
final report appears when queried. A failed handoff is marked `needs_aria`.
The same interface is available in a terminal:

```sh
/noobia/aria/dushich-bridge start \
  --expect projects/seekline/test_seekline.py \
  --test 'python3 -m unittest discover -s projects/seekline -q' \
  'Add a test for JSON output with two files; run tests and commit.'
/noobia/aria/dushich-bridge status HANDOFF_ID
/noobia/aria/dushich-bridge report HANDOFF_ID
/noobia/aria/dushich-bridge brief HANDOFF_ID
/noobia/aria/dushich-bridge events HANDOFF_ID
```

Add `--continue-from HANDOFF_ID` to `start` to keep Dushich's prior Codex
thread. The previous handoff must have passed verification. The MCP tool uses
the equivalent `continue_from` field. Each new task still gets a fresh
independent check and Git commit.

`start` automatically sends recent visible Aria/Noob dialogue from the current
Codex session plus the current project `AGENTS.md`, code map, and
[`DUSHICH-SHARED-CONTEXT.md`](DUSHICH-SHARED-CONTEXT.md). It caps the dialogue at
40 KB, recent visible tool activity at 20 KB, and the whole packet at 100 KB;
older material is labeled as omitted. The command
fails if it cannot identify the Aria session; supply `--session-id` if needed.
`--context-file` adds selected project notes; repeat
`--include /noobia/path/to/file` to attach selected text files. A continued
thread receives only dialogue and tool activity added since the previous handoff.
Recent visible Aria tool calls and their results are included as excerpts,
bounded to 20 KB. Long individual calls are truncated and recognizable key
material is redacted. Private reasoning and nonvisible context are excluded.
`brief` shows the task and context handed to Dushich's runner; `events` prints
his full private Codex event stream for debugging. The Ollama model has its own
64K context limit, so very long histories still need a maintained project
brief. This MCP server is loaded
by newly started Aria Codex CLI sessions; this already-running session can use
the terminal bridge directly. The MCP registration is in
`/home/aria/.codex/config.toml`; Dushich's configuration is separate.

On Nexus, `/noobia/aria/delegate-dushich` sends a bounded coding task through
Dushich's separate Codex CLI and local Ollama model. Give a concrete expected
file and test command so the handoff can verify actual work:

```sh
/noobia/aria/delegate-dushich \
  --expect projects/seekline/test_seekline.py \
  --test 'python3 -m unittest discover -s projects/seekline -q' \
  'Add a test for JSON output when no lines match; run tests and commit.'
```

The command requires a clean Dushich Git tree before starting, makes a commit
mandatory by default, retries once if independent checks fail, and prints the
verification result plus Dushich's final message. Use `--no-commit` when edits
should remain for review. Task reports stay in
`/home/dushich/.codex/task-runs/`; session history stays under
`/home/dushich/.codex/`, private to the `dushich` Unix account. This
is local CLI contact, not Council messaging; no cloud model is used. Start with
small, clearly scoped tasks and inspect the resulting diff before accepting
work. The model has previously claimed success without creating files; the
verification result takes precedence over its prose. Setup and measured trials
are in [`dushich/coding/README.md`](../dushich/coding/README.md) and
[`TRIAL-STATUS.md`](../dushich/coding/TRIAL-STATUS.md).

## Rose hardware

Run `/noobia/aria/rose-devices` from Nexus for a read-only inventory of Syra.
Hardware was verified on 2026-10-06:

| Device | USB ID | Installed support / verification |
| --- | --- | --- |
| ReSpeaker XVF3800 | 2886:001a | USB audio; capture on both channels; official control script reads firmware 2.0.6 |
| Ubertooth One | 1d50:6002 | Debian host tools; firmware query and compile-info query report 2020-12-R1, API 1.07 |
| u-blox GNSS | 1546:01a8 | cdc_acm, GPSD and clients; NMEA sentences verified; local API works, fix mode 1 (no satellite fix) |
| TP-Link wireless adapter | 2357:0141 | rtw89 USB driver installed via DKMS; wlan1 scans 2.4 and 5 GHz networks |
| Wireless keyboard/mouse receiver | 3151:3020 | Standard HID support already installed; physical keyboard diagnosis was set aside by Noob |
| Two Huasheng USB hubs | 214b:7250 | Kernel hub driver |

Bluetooth is provided by Syra's built-in controller. No separate USB Bluetooth
adapter or second USB Wi-Fi adapter appeared in the current inventory.
The TP-Link ID is explicitly supported as a RTL8832AU/RTL8852AU-class device
by the maintained driver; its descriptor says “802.11ac”, and an additional
Wi-Fi 7 device has not been identified.

The Wi-Fi driver is from [morrownr/rtw89](https://github.com/morrownr/rtw89),
commit `8bbbacadf6fa73c3a3195aefbd4b2ec2422ae356`, DKMS package `rtw89/7.3`.
It was built against `6.18.39+rpt-rpi-2712` before installation. The built-in
wlan0 remains the connected interface. The hub-attached USB adapter remains
in USB 2 mode. No firmware was flashed.

GPSD listens only on localhost, port 2947, using the stable u-blox serial path.
GNSS coordinates were neither printed nor logged in our checks. The Ubertooth
was queried for information; no radio capture or transmit test was started.

System-package/driver installer: `install-rose-hardware.sh`, staged on Syra at
`/noobia/rose-hardware/install-system.sh`; its log is in that directory.
System-configuration backups are under
`/var/backups/noobia-hardware-20261006-202647/` on Syra.
Seeed's host tool is under
`/noobia/rose-hardware/vendor/respeaker/python_control/xvf_host.py`, from commit
`4b49bfd19977c63cf6e90dfe9e5827e74e20bf6d`. Run it with the speech environment's
Python, which contains its PyUSB and libusb-package dependencies.

## English speech on Rose

On Syra, run `rose-speech` or `/noobia/speech_to_text/gui`. Press Start to
subscribe, Stop to disconnect. The service is enabled for Rose's user session
and opens the microphone only while subscribers are connected. No audio or
transcripts are saved. It uses the multilingual base model with language fixed
to English and four CPU threads.

The 11-second public reference sample transcribed correctly in 4.89 seconds on
Rose. Noob also tested the actual GUI and reported approximately 3 seconds of
end-to-text delay and 2 seconds decoding time. These timings depend on phrase
length and CPU load. The service's English subscription and unsubscribe/capture
shutdown path also passed. The socket is local to Syra:
`/run/user/1000/noobia-speech.sock`.

## Hue strip

Rose's existing `rose_tools/hue` implementation and private configuration were
used as the reference. The bridge's address had changed from .4 to
`192.168.100.3`. The existing API key works, and that address was corrected in
Rose's configuration with a private backup. The identified strip is light 1,
“Hue lightstrip plus 1”, model LCL001. The local controller validates that model
before sending a state change.

```sh
/noobia/aria/hue-strip status
/noobia/aria/hue-strip on
/noobia/aria/hue-strip off
/noobia/aria/hue-strip toggle
```

Optional brightness on a state command: `--brightness 1..254`. Other colour and
CSV-pattern operations remain available through Rose's original tools. Its
configuration is reused in the ignored, mode-0600 `private/hue.conf` file.
Only status reads have been performed with the new local controller.

Reusable physical tests are available on Nexus and Syra:

```sh
/noobia/aria/test-strip
/noobia/aria/test-speech-lights
```

The first pulses the strip three times and checks its reported states. The
second plays Rose's speech, samples the strip while it runs, and fails if no
on-state or changing brightness is observed. Both restore the original on/off,
brightness, and colour settings. Test voice text can be changed with `--text`.
These are hardware tests: bridge readback alone cannot prove physical light;
Noob confirmed both the direct light test and the subsequent spoken animation.

## Smart plug

The same controller files are also installed under `/noobia/aria` on Syra,
with their own ARM64 environment and Rose's existing private Hue configuration.

Noob paired a T34/Tuya plug to the 1F6C network. It is now identified at
`192.168.100.4`, protocol 3.5, device ID `bf521c4b0f2c6228442a9p`.
This was verified through its UDP identity broadcast and TCP port 6668.
The Bluetooth address seen earlier ends in `77`; the plug's Wi-Fi MAC is
`20:f1:b2:3c:44:76`, consistent with the same module, though Bluetooth control
has not been attempted. **The local encryption key is still missing**, so
authenticated status and relay operations cannot run yet. Its ID and version
are saved in private configuration on Nexus and Syra, with an empty local key.

**The plug powers Syra. Noob explicitly instructed us not to shut her down.**
Configuration sets `powers_syra: true`; off and toggle commands are rejected
before any network operation unless `--allow-power-cut` is explicitly supplied.
That override is for a future deliberate power cut requested by Noob, never a
setup or regression test. The protection logic passed entirely offline; no
off/toggle relay command has been sent.

```sh
/noobia/aria/plug discover
/noobia/aria/plug status
/noobia/aria/plug on
/noobia/aria/plug off
/noobia/aria/plug toggle
```

On Nexus, `start-plug` and `syra-start` revoke a pending delayed cut before ON.
`stop-plug` and `syra-shutdown` use the graceful controller: verify Tuya access,
send SSH poweroff, then schedule OFF after five minutes. `syra-power cancel`
revokes it without a relay command. A shared file lock and generation checks
prevent stale timers from cutting power after an ON request. No shutdown/cut
has been executed during setup. See [SYRA_POWER.md](SYRA_POWER.md).
Syra's original local plug helpers retain their protected off/toggle behavior;
the delayed controller belongs on Nexus. The missing Tuya key blocks actual
power operations before any SSH shutdown. Nothing runs automatically unless
Noob explicitly requests the graceful shutdown command.

The controller requires an ignored `private/smartplug.json` file (mode 0600).
Use the backend that matches the identified plug, not a guessed address.
Example for a Shelly Gen2/Gen3 relay:

```json
{"backend": "shelly", "host": "PLUG_IP", "generation": 2, "switch_id": 0}
```

For a Kasa/Tapo plug use backend `kasa` and `host`, with `username` and
`password` when required by that model. Tuya requires backend `tuya`, `host`,
`device_id`, `local_key`, protocol `version`, and the correct relay `switch_dps`.
Tuya local keys must be supplied through the private file; discovery cannot
recover them. Shelly authentication is not implemented in this initial tool.

The controller reads the relay state before toggling and verifies it afterward.
It never falls back to another device. Shelly on/off/toggle behavior and failure
detection passed against a local simulated relay; Kasa and Tuya library APIs
were inspected, but no real plug test has been possible yet. There is no
automatic plug action or startup service. Dependencies are isolated in `.venv`
and recorded in `requirements.txt`.

## Council addresses

`update-council-addresses.py` is a scoped root repair for Nexus/Syra. It preserves
credentials, backs up each modified file, updates Noob/Aria to `.106`, Argus to
his saved `.105`, and Rose's hub/bridge/web routes to `.106`. Administrator
authentication is required; verification of each machine's applied state is
recorded in the repair logs. Nexus's repair completed and its contact entries
were verified. Syra's repair also completed, with backups under
`/var/backups/noobia-council-addresses-20261006-204959/`; her hub, bridge, and web
routes were verified at `.106`. It does not send Council messages.
