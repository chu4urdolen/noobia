# Autonomous Republic of Noobia: Lynx (OnePlus Nord 3 / MT6983)
## Operational Tools, Services, & Architecture Reference

*Audited and recorded on 2026-11-25 by Banshee and Dushich. Checked against the live
phone and extended the same day by Gwyn (sections 5-11 and inline corrections marked "Gwyn:").
This is the living spec: update it when Lynx changes.*

**Contents:** 1 Platform & storage · 2 Core services · 3 Agent tools (overview) · 4 Special mechanics · 5 Power modes & START · 6 Guards & watchers · 7 Boot chain & hard rules · 8 Hardware & cameras · 9 Senses -> events (summary) · 10 Autonomy pipeline & brain · 11 Open issues · **12 Every agent tool** · **13 Every sense** · **14 The senses DB (pattern store)**


---

## 1. System Platform & Storage Architecture

* **Hardware:** OnePlus Nord 3 5G (CPH2493), MediaTek Dimensity 9000 (MT6983).
* **OS:** Alpine Linux v3.24 (aarch64, musl libc, OpenRC init).
* **Storage Persistence:**
  * Root filesystem (`/`) is mounted read-write on the internal UFS flash partition `/dev/sdc85` (ext4, ~218.7 GB total, >208 GB free).
  * All binaries, scripts, libraries, package databases (`/etc/apk/world`), configurations, and OpenRC runlevels (`/etc/runlevels/default`) are durable and survive reboots.
  * Filesystem writes are flushed to persistent flash via `sync`.
* **RAM Filesystem (`tmpfs`):**
  * `/run` is mounted on tmpfs (size 128 MB). Holds transient PIDs, Unix sockets (`/run/lynx/noobd.sock`), and dynamic non-blocking concurrency locks (`/run/lynx/locks/`). Ephemeral locks automatically vanish across boots to prevent stale locks.
  * In-flight microphone PCM audio clips are captured only in RAM and deleted immediately after speech recognition.

---

## 2. Core Services (OpenRC `default` Runlevel)

All registered services in `/etc/runlevels/default/` auto-start on boot:

### Autonomy & Perception
* **`lynx-senses`** (`/usr/local/lib/noobia/senses/common/lynx_senses_loop.py`):
  Continuous sampled loop running senses:
  * S2 Touch (tap/hold detection every 2s)
  * S3 Wi-Fi (carrier transition and signal strength)
  * S4 Power (battery level, thermal metrics, charging state)
  * S8 Nexus (connectivity heartbeat probe)
  * S9 Hearing (microphone level sampling every 10s; disabled by default)
  * Auxiliary senses: light, motion, proximity, compass/magnet wand, tri-state alert slider.
* **`lynx-camera-sense`** (`/usr/local/lib/noobia/senses/camera/lynx_sense_camera.py --loop --every 60`):
  Dedicated 60-second vision sense loop controlling front, back, and wide cameras. Includes night brightening and a 300s cooldown on `camera.dark` to prevent dark room alert spam.
* **`noobia-autonomyd`** (`/usr/local/lib/noobia/autonomy/autonomyd.py`):
  Autonomous harness daemon. Chunks incoming syslog sense lines into 20-second observation windows, matches pattern rankers against `patterns-lynx.json`, and queues prioritized jobs.
* **`lynx-agent-worker`** (`/usr/local/bin/lynx-agent-worker`):
  Background job dispatcher. Dequeues jobs and runs `lynx-agent`, sending formatted prompts to local Qwen 27b over Ollama on Nexus.

> **Gwyn:** these four were taken OFF the boot runlevel on 2026-11-23 for the
> power-saving START screen (section 5): `lynx-power-mode active` starts them, POWER SAVE
> and the guards stop them. On 2026-11-25 all four are back in `/etc/runlevels/default`
> (re-added by someone since), so after a reboot they run while the screen shows START.
> See Open Issues (section 11).

### Hardware & Platform Daemons
* **`lynx-noobd`**: NRP (Noobia Remote Protocol) daemon connecting local hardware sockets (`/run/lynx/noobd.sock`) to the Nexus LAN.
* **`lynx-display`**: the portrait UI on the AMOLED (`/usr/local/bin/lynx-portrait-display`, source `lynx/tools/lynx_drm_dmabuf_pattern.c`): HOME / CHAT / INPUTS / OUTPUTS / STATUS / RADIO / DEBUG pages, the POWER SAVING page with START, and on STATUS the AIGEL mode, DEBUG MODE, POWER SAVE and two-tap SHUT DOWN buttons. *(Gwyn: not `lynx-console`.)*
* **`lynx-console`**: separate service; the shell console page (`/bin/ash` over `/run/lynx-console/control.sock`).
* **`lynx-audio`**: ALSA sound subsystem and mixer initialization.
* **`lynx-media`**: Local media playback server (`lynx-media serve`) for sound clips and visuals. *(Gwyn: NOT in the boot runlevel; started by START / `lynx-power-mode active`, like `lynx-bluetooth`.)*
* **`lynx-flashlight`**: Flashlight LED driver.
* **`lynx-haptic`**: Linear haptic vibration pulse driver.
* **`lynx-sensorhub` & `lynx-sensor-retry`**: Hardware sensorhub interface (`/dev/hf_manager`).
* **`lynx-charging-stack`, `lynx-charge-guard`, `lynx-battery-reserve`**: Power management, intelligent charge throttling, and low-battery protection.
* **`lynx-heat-recorder`**: Background temperature logging across all thermal zones.
* **`lynx-time-sync` & `lynx-maintenance` & `lynx-tidy` & `lynx-local-logs`**: Chrony time sync, log rotation, and system maintenance.
* **`lynx-wifi` & `lynx-dropbear`**: WPA supplicant networking and secure dropbear SSH daemon.
* *(Gwyn, also in the runlevel:)* **`lynx-health`** (HASH-PINNED by the boot hand-off - never edit), **`lynx-power-boot`** (writes `saving boot` to `/var/lib/noobia/power-mode` before the display starts), **`lynx-watchers-swap`** (replaces the boot image's RAM watchers with the safe ones), **`lynx-power-history`**, **`noobia-quiet-trace`**.

---

## 3. Operational Agent Tools

Available in `/usr/local/share/lynx/agent-tools/` and `/usr/local/bin/`:

### A. Expressive & Physical Actions
* **`lynx_speech`**: Vocal speech synthesis via Flite TTS (`lynx-speech`).
  * **Rule:** Must always accompany physical actions (flashlight, haptics, chimes) so she never acts in silence.
* **`lynx_flashlight_pulse`**: Flashlight pulse.
* **`lynx_haptic_pulse`**: Haptic buzz.
* **`lynx_display_status`**: Screen display and visual updates.
* **`lynx_media_play`**: Audio chime and image playback.
* *(Gwyn:)* a `SENSE:` call is offered exactly five tools - `lynx_speech`, `lynx_haptic_pulse`, `lynx_flashlight_pulse`, **`lynx_display_pose`**, `lynx_media_play` (its description lists the sound and image names, so no catalog lookup is needed) - and the agent refuses any other (`SENSE_TOOLS` in `lynx/tools/agent/lynx_agent.py`). All 44 tools are available to `CHAT:`.

### B. Cyber-Recon & Network Diagnostics (`lynx_net_diag`)
Autonomous network auditing suite. Supports `--fork` (`fork: true`) and non-blocking locks:
* `net-ifaces`: Interface enumeration, operational state, IP addresses, MTU.
* `lan-sweep`: ARP neighbor discovery on local subnet.
* `wifi-recon`: Wi-Fi AP airspace discovery (SSID, BSSID, channel, signal strength).
* `port-scan`: Open port audit on local host or specified target.
* `vuln-check`: Security posture check (SSH, remote services, listening sockets).
* `ssl-audit`: SSL/TLS certificate inspection, validity, and expiry.
* `dns-audit`: DNS resolver latency and query resolution check.
* `traceroute`: Path hop latency and route discovery.
* `packet-sample`: Live packet capture sample via tcpdump.

### C. 5G & Cellular Diagnostics (`lynx_cellular_diag`)
Autonomous cellular auditing suite for the MediaTek M80 5G modem:
* `sim-check`: Dual-SIM hardware tray detection, slot presence, and kernel hotplug node status.
* `modem-status`: MediaTek MT6983 MD1 baseband state, 53 CCCI character channels, and modem daemon readiness.
* `5g-bands`: OnePlus Nord 3 radio frequency audit: 13 5G NR bands (n1, n3, n5, n7, n8, n20, n28A, n38, n40, n41, n66, n77, n78) with 4x4 MIMO and 21 LTE bands.
* `ccmni-stats`: Kernel packet data routing interface audit (ccmni0 through ccmni20, ccmni-lan).
* `cell-recon`: ModemManager carrier network and cell tower scan.
* `at-probe`: Direct CCCI AT channel probing.

### D. Observability & Tracing
* **`lynx-stream-log`** (`/usr/local/bin/lynx-stream-log`):
  Comprehensive pipeline stream inspector on Lynx and Nexus. Tracks sense chunks, chunk priority, ranker patterns, queued prompts, model latencies, tool execution arguments/results, and spoken dialogue.

---

## 4. Special Mechanics & Behavioral Logic

### 1. Hearing Sense & Acoustic Spam Guard
* **Disabled by Default:** By design, the hearing sense is disabled by default to prevent ambient acoustic noise from flooding her sensory loop with unnecessary Whisper processing.
* **Toggle Controls:**
  * **Nexus Dashboard Button / API:** `http://192.168.100.106:112/api/v1/hearing` (`{"enabled": true/false}`). *(Gwyn: currently DOWN - it is served by `aigel_intake`, which is disabled since 2026-11-24. Use the file.)*
  * **Local File Override:** `/var/lib/noobia/senses/hearing/enabled` (`1` / `0`). If the file exists it wins; it is re-checked right before every clip.
* **Operation:** When enabled, sound spikes (`peak >= 80` or `rms >= 25.0`) trigger a 4s in-memory PCM capture sent to Nexus Whisper STT (*Gwyn:* `http://192.168.100.106:5052/hear?rate=48000` from Lynx; `localhost:5052` only on Nexus). Spoken words emit `NOOBIA P20 hearing speech | <words>` into syslog and are answered vocally by Qwen.
* *(Gwyn:)* the same clip also yields `hearing sound | <label>` (top AudioSet class, e.g. knock, music; each label at most every 120 s) and the level sampler emits `hearing startle` (RMS >= 8x the room and >= 400; 30 s cooldown). Nexus `nexus_hear.service`: AST classifier (~1.2 s) first, Whisper-small (~3.6 s) only when AST hears speech, with a names prompt (Lynx, Tom, Noobia, the Noobs' names). Capture tool: `/usr/local/bin/lynx_microphone_clip.py` (mixer route `hw:0,11`, 48 kHz mono, PCM to stdout only).

### 2. Forked Diagnostic Execution & Feedback Loop
* Diagnostic tools invoked with `fork: true` detach into the background in ~15 ms, allowing the main agent turn to conclude immediately without waiting on network probes.
* The background worker formats findings into natural conversational sentences and writes them directly to `noobia-sense` syslog.
* The autonomy ranker picks up these new diagnostic events and feeds them back into her perceptions as fresh knowledge.

### 3. Concurrency Protection
* Non-blocking file locks in `/run/lynx/locks/{tool}_{action}.lock` use kernel `fcntl.flock`.
* If a diagnostic action is already in flight, duplicate attempts bail out cleanly with an advisory message instead of spawning duplicate processes.
* Because locks live on `tmpfs`, any crash or reboot cleans all locks automatically.

### 4. SENSE vs CHAT Execution Modes
* **`SENSE:` Triggers:** Execute in exactly **one round** with required tools. Qwen takes direct physical/verbal action in sub-second response times. *(Gwyn: Qwen's own work is 0.1-0.8 s, but end to end a reaction takes 8-70 s, because Ollama serves one request at a time and other callers' long prompts evict the cache - see section 11.)* Thinking is off (`reasoning: {effort: none}`).
* **`CHAT:` Dialogue:** Supports multi-round execution (up to 3 rounds) for conversational inquiry and tool reading.

### 5. Safety Rules & Hardware Protection
* **Principle 10 (Quiescence over Termination):** Under thermal or battery stress, Lynx must throttle workloads and wait rather than initiating autonomous reboots or hard shutdowns.
* **Watchdog Protection:** Never execute recursive filesystem commands (`grep -r`, `find -exec`) on Lynx userspace; always use single named file reads to avoid tripping the SoC hardware watchdog.

---

*Sections 5-11 added by Gwyn on 2026-11-25, checked against the live phone (uptime 4.3 h).*

## 5. Power Modes & the START Screen

* Mode file: `/var/lib/noobia/power-mode` - `active`, `debug`, or `saving <reason>`. Tool: `/usr/local/bin/lynx-power-mode active|debug|saving [reason]|status` (source `lynx/linux-port/lynx-power-mode.sh`, lock `/run/lynx/power-mode.lock`).
* **Boot mode** (`lynx-power-boot`): `active` when Lynx's services are in the default runlevel (true since 2026-11-25), otherwise `saving boot`. The display shows POWER SAVING with battery %, CPU temperature, the reason, and one **START** button.
* **START** runs `lynx-power-mode active`: makes sure `lynx-media lynx-noobd` run (always on), starts `lynx-bluetooth lynx-agent-worker noobia-autonomyd lynx-senses lynx-camera-sense` and switches to HOME. **POWER SAVE** (STATUS page, between AIGEL and SHUT DOWN) stops them in reverse order and shows START. The display follows the mode file every second, whoever changed it.
* **DEBUG MODE** (STATUS page button, or `lynx-power-mode debug`): stops all AI cognition services (`lynx-agent-worker` and `noobia-autonomyd`), while keeping all sensory services (`lynx-senses`, `lynx-camera-sense`, `lynx-radio`, `lynx-bluetooth`, `lynx-media`, `lynx-noobd`) running. Opens the 3-pane interactive Lab on the portrait display:
  - **Pane 1 (Left):** Scrollable tool catalog (all 45 tools). Tapping a tool selects it.
  - **Pane 2 (Right):** Selected tool arguments editor, preset buttons (`{} EMPTY`, `SAMPLE`, `CLEAR`), and `> TEST TOOL <` execution button.
  - **Pane 3 (Bottom):** Live sensory and tool outputs feed with a mode toggle button between `MODE: RAW (PRE-REGEX DB)` (raw sense/tool output) and `MODE: REGEX DB (TRANSLATED)` (natural English sentences rendered through `patterns-lynx.json` / `patterns.json`).
  - Top header has an `EXIT / RESUME (AI ON)` button to cleanly restore normal active AI mode.
* Always on in both modes: Wi-Fi, SSH, display, logs, charging, watchers, heat recorder, NRP daemon. The Nexus camera keeper does not prepare the camera while she is in power saving.
* **SHUT DOWN** needs two taps within 5 s (`openrc-shutdown --poweroff now`); it is a person's choice, never automatic.

## 6. Guards & Watchers (Principle 10)

* Safe RAM watchers, put in place by `lynx-watchers-swap`: `/run/lynx/thermal-watch.sh` (CPU >= 75 C), `/run/lynx/battery-watch.sh` (battery >= 50 C, or <= 10 % and not charging), `/run/lynx/lynx-health-supervisor.sh` (10 consecutive failures). They act only after **10 readings in a row**, and they **never power off or reboot**: they call `lynx-power-mode saving "<reason>"` (back to the START screen, reason shown) and throttle the CPUs.
* **Guard switch** `/etc/lynx/power-thermal-guard.disable` (present, and meant to be): the watchers still act (power saving with the reason) and only skip the CPU throttle. What it really disables are the old strict guards *inside her tools* (e.g. the mic refused to record above 35 C battery), which Tom asked to remove ("45 is fine"). Keep it.
* `lynx-charge-guard` steps the charger input current down at 38/40/42 C. `lynx-maintenance` only throttles.

## 7. Boot Chain & Hard Rules

* V53 `boot_a`: an early BusyBox stage (SSH port 22) hands off to Alpine/OpenRC (SSH **port 2222**, IP 192.168.100.107). The hand-off checks pinned SHA-256s of `/sbin/openrc-init`, `/lib/ld-musl-aarch64.so.1` and **`/etc/init.d/lynx-health`**, temperatures below 48 C, and Nexus confirmation. **Editing a pinned file makes every boot refuse the hand-off** (rescue recipe: `lynx/logs/rescue-20261122/restore.sh`). The V54 no-poweroff tail is a proposal only, not flashed.
* Never write anything that reboots or powers Lynx off. Never use camera `G/S_EXT_CTRLS` (kernel crash); `/usr/sbin/v4l2-ctl` is a guard wrapper.
* Installing on BusyBox: there is no `chmod --reference`, and root's umask is 077, so `cat > f.new && mv` yields mode 600 - read `stat -c %a` first. Restart a service only if it was running (`rc-service X status | grep -q started && rc-service X restart`). Merge `/var/lib/noobia/autonomy/patterns.json` only with `noobia-autonomyd` stopped, keeping live-only patterns.
* Fastboot recovery: `lynx/tools/platform-tools/fastboot` (slot a).

## 8. Hardware Details

* 8 CPU cores, 15.4 GB RAM, kernel `5.10.149-android12-9`, Alpine 3.24.2.
* **Cameras** (CAMSV-0, one at a time; route by `media-ctl` on `/dev/media1`; stack prepared per boot by `noobia-lynx-camera-keeper` on Nexus, with boot-loop-safe markers in `lynx/state/camera-keeper/`):
  * rear **wide** IMX355, sensor2, 3264x2448, RGGB - her main eye;
  * rear **macro** GC02M1, sensor4, 1600x1200, RGGB - called `back`, used every 5th look and as the resting route;
  * **front** S5K3P9SP, sensor1, 2320x1744 binned, **GBRG** (`phase=gbrg`) - first frames 2026-11-24;
  * rear main IMX890 - untested.
  Each look = rear (wide, or macro every 5th) + front, about 70 s. Capture helper: `/usr/local/libexec/lynx/lynx-camsv-capture`; lock `/run/lynx/camera.lock`. No auto-exposure: night frames are near-black, and Nexus brightens them.
* **Sensors:** BMI260 accelerometer/gyro via `/dev/hf_manager` (`lynx-hf-sample`, 12.5 Hz, <= 16 events per call), AK09918 magnetometer, ambient light, proximity, touchscreen (NRP queue), microphone `hw:0,11`, tri-state alert slider.

## 9. Senses -> Events (all lines emitted as **P20**)

* Motion (1 s bursts): `position.change` (45 degrees, held 30 s), `pickup`, `placed`, `shaken` (3 samples > 0.15 g), `freefall`, `rocked` (0.3-1.2 Hz).
* Camera: `objects.seen` (scored YOLO labels plus a caption), `scene.seen` (caption only), `dark` ("too dark to see much"; at most every 300 s per camera). Florence's photo framing is stripped from captions.
* Hearing: `speech`, `sound`, `startle`, plus `sound.heard` while Nexus hearing is not answering.
* Also: touch tap/hold, light, proximity, power/thermal (battery `temp.change` of 5 C, checked once a minute), Wi-Fi, Nexus link, network, compass/magnet, slider, telepathy, and routine `status.sample` lines.
* `REACTION_PRIORITY` (env `LYNX_REACTION_PRIORITY`, default 20; 0 keeps each sense's own priority) in `lynx/senses/common/lynx_senses_lib.py`.

## 10. Autonomy Pipeline & Brain

* Sense line -> `noobia-autonomyd` (`/etc/noobia/autonomy.json`: `window_s 20`, `max_lines 15`, `uniform_priority 20`, `carry_priority false`, `combine true`, `async_aigel true`, **`aigel.enabled false`**) -> pattern DB (`/var/lib/noobia/autonomy/patterns.json`, 39 live) -> **one combined sentence per chunk** (`SENSE: <unique sentences>`) -> agent job queue `/var/lib/lynx-agent/jobs` -> `lynx-agent-worker` -> `lynx-agent`.
* Unmatched lines: to Aigel when she is on; while Aigel is off, straight to Lynx (except `*.status.sample` and `heartbeat`). Patterns on `status.sample` never speak (`to_noob false`).
* **Aigel is disabled** (Tom, 2026-11-24): on Lynx `aigel.enabled false`; on Nexus `aigel_intake` and `aigel_learning_loop` are stopped and disabled (her health monitors still run). Restore: `systemctl enable --now` both, and set `aigel.enabled true`.
* Brain (`/etc/lynx/brain.json`): `nexus-qwen` qwen3.8:27b via `http://192.168.100.106:8080/v1` (`noobia-inference-proxy`, timeout 60 s) -> `local-qwen` -> `cloud-openai` gpt-5.4-mini (30 s).
* `CHAT:` comes from the chat screen (`/usr/local/bin/lynx-chat-send`, mode 700, run directly by the display).
* Logs on Lynx: `/var/log/lynx/messages` (syslog, sense lines, `deliver status`), `/var/log/lynx-agent.jsonl` (backend and tool events), `/var/lib/noobia/lynx_thought.txt` (what she said).

### Nexus services Lynx depends on
| Port | Service | Role |
| --- | --- | --- |
| 5050 | `nexus_detect` | `/detect_bayer?w=&h=&phase=`: decode, YOLOv8n, brighten dark frames, 2x zoom tiles |
| 5051 | `nexus_vision` (localhost) | YOLO11x + Florence-2-large on CPU |
| 5052 | `nexus_hear` | AST + Whisper-small on CPU |
| 8080 | `noobia-inference-proxy` -> Ollama | qwen3.8:27b (also serves Dushich and the other Noobs) |
| - | `noobia-lynx-camera-keeper` | prepares the camera stack after each boot |

## 11. Open Issues (2026-11-25)

1. **Reaction latency:** Qwen serves one request at a time; callers with 3k-41k-token prompts evict each other's cache. Unknown `/api/chat` callers are still active with Aigel off. Options for Tom and Aria: give Lynx's reflexes priority, `OLLAMA_NUM_PARALLEL=2` if VRAM allows, or a small model for her reflexes.
2. ~~Boot runlevel vs START~~ - resolved (Tom: "enable everything"): the services stay in `default`, and `lynx-power-boot` now boots `active` when they are there (else `saving boot` with START). Also fixed: POWER SAVE used to stop `lynx-noobd` (it needs `lynx-media`); media and noobd now stay on in both modes.
3. ~~Guard switch~~ - resolved: the watchers act with it set; it only disables the old in-tool guards (keep it).
4. **`lynx_net_diag` / `lynx_cellular_diag`** include `port-scan`, `vuln-check`, `packet-sample` (tcpdump) and `at-probe`. They are not offered to SENSE calls, but CHAT can use them. Suggested: limit targets to Noobia's own LAN and devices, and ask before a packet capture (other people's traffic - Principle 8). `at-probe` writes to the modem: treat it like a physical action.
5. ~~Front camera~~ - resolved: `lynx_camera_photo` / `take_photo` updated to capture both front (S5K3P9SP) and rear cameras simultaneously by default, returning detections in front and behind.
7. ~~Flashlight feedback loop~~ - fixed by Banshee (`ebe26d3`): light changes within 3.5 s of her own flash are ignored. Magnet wand recalibrated (150 uT jump / 450 uT absolute).
6. The recursive-`grep`/`find` watchdog rule is Banshee's field observation; worth a reproducible receipt before it hardens into lore.

---

## 12. Every Agent Tool

All tools live in `/usr/local/share/lynx/agent-tools/` as a manifest (`<name>.json`: description, JSON-schema arguments, timeout) plus a script (`<name>.sh`, JSON on stdin). `lynx-agent` turns them into function tools for Qwen. Arguments: `*` = required, `a|b` = allowed values.

### Intuitive Agent Tool Aliases (2026-11-28)

To give Lynx's local LLM agent clear self-evident understanding of each tool from its name, intuitive action-oriented aliases are deployed alongside canonical tools (full backward compatibility preserved):

| Intuitive Alias | Canonical Tool | SENSE Call | What it does |
| --- | --- | --- | --- |
| `speak` / `lynx_speak` | `lynx_speech` | ★ | Speak aloud with Flite TTS & display thought on screen |
| `take_photo` / `lynx_take_photo` | `lynx_camera_photo` | ★ | Capture picture with cameras (default: both front & rear) & analyze via vision models |
| `turn_on_flashlight` | `lynx_flashlight_pulse` | ★ | Pulse rear flashlight LED (100 ms) |
| `turn_off_flashlight` | `lynx_flashlight_stop` | ★ | Ensure flashlight LED is turned off |
| `vibrate` | `lynx_haptic_pulse` | ★ | Haptic pulse (80 ms tactile buzz) |
| `stop_vibration` | `lynx_haptic_stop` | ★ | Ensure haptic motor is stopped |
| `play_sound` | `lynx_media_play` | ★ | Play sound (beep, chime, double_beep) or display image |
| `stop_sound` | `lynx_media_stop` | ★ | Stop audio playback or clear image |
| `set_display_pose` | `lynx_display_pose` | ★ | Update display portrait expression or animation |
| `scan_network` | `lynx_net_diag` | - | Network interface, ping, ARP, and LAN discovery diagnostics |
| `scan_cellular` | `lynx_cellular_diag` | - | Cellular SIM state, APN, signal, and radio bearer diagnostics |
| `capture_air_traffic` | `lynx_capture_air_traffic` | - | Over-the-air packet capture (Wi-Fi & cellular ccmni0) and multi-channel sweep without dropping connection |
| `read_light_sensor` | `lynx_light_read` | - | Read ambient light sensor (TCS3408) |
| `read_motion_sensors` | `lynx_motion_read` | - | Read accelerometer or gyroscope motion vectors |
| `read_compass_sensor` | `lynx_magnetometer_read` | - | Read magnetic compass sensor (AK09918) |
| `read_proximity_sensor` | `lynx_proximity_read` | - | Read optical proximity sensor (TCS3701) |
| `save_memory_note` | `lynx_note` | ★ | Save personal memory note to persistent FTS5 database |
| `manage_reflexes` | `lynx_reflex` | ★ | Inspect or register autonomous sensory-action reflex rules |
| `lynx_camera_status` | `lynx_camera` | - | Check camera ISP and hardware validation status (read-only) |
| `lynx_flashlight_status` | `lynx_flashlight` | - | Check flashlight driver and hardware state (read-only) |
| `lynx_bluetooth_status` | `lynx_bluetooth` | - | Check Bluetooth controller (HCI0) readiness (read-only) |
| `lynx_gps_status` | `lynx_gnss` | - | Check GNSS receiver interface status (read-only) |
| `lynx_mic_status` | `lynx_microphone` | - | Check microphone hardware interface status (read-only) |
| `lynx_sample_audio_level` | `lynx_microphone_level` | - | Sample bounded 1s microphone audio level (RMS & peak) |

### Expressive (what she uses to react; the only tools a `SENSE:` call is offered are marked ★)

| Tool | Arguments | Timeout | What it does |
| --- | --- | --- | --- |
| `lynx_speech` | `text*` | 15 s | ★ Speaks one or two sentences aloud with Flite TTS and shows them on screen as her thought. Her main voice; a reaction that is spoken counts as her answer. |
| `lynx_haptic_pulse` | - | 6 s | ★ One 80 ms buzz through the NRP runtime, then verifies the motor is off. A nudge, a purr, a startle. |
| `lynx_flashlight_pulse` | - | 8 s | ★ One 100 ms flash of the rear LED; checks battery/thermal health, verifies OFF, 10 s cooldown. The light sense ignores changes for 3.5 s afterwards (no feedback loop). |
| `lynx_display_pose` | `action=status|list|pose|animate*, pose` | 10 s | ★ Shows a portrait pose or animation on HOME: 01_standing_smile, 02_talking, 03_look_left, 04_look_right, 05_using_device, 06_singing, the dance frames, or the `dance` animation. `action=list|status` only read. |
| `lynx_media_play` | `kind=sound|image*, item*` | 8 s | ★ Plays one sound (beep, chime, double_beep) or shows one image from her catalogue. In a SENSE call the names are written into its description. |
| `lynx_media_stop` | `kind=sound|image*` | 8 s | Stops and clears the sound or image channel. |
| `lynx_flashlight_stop` | - | 5 s | Requests the flashlight OFF and reports whether the driver confirmed it; safe without a driver. |
| `lynx_haptic_stop` | - | 6 s | Requests the vibration motor OFF and verifies it. |

### Looking and listening on demand

| Tool | Arguments | Timeout | What it does |
| --- | --- | --- | --- |
| `lynx_camera_photo` | `camera=both|front|wide|back` | 45 s | Takes pictures with cameras (default `both`: front S5K3P9SP and rear IMX355) and returns what Nexus detects; also writes `cause=self` sense lines so her senses know she looked. |
| `lynx_microphone_level` | - | 10 s | One bounded 1 s microphone level sample (late RMS and peak), keeps no audio, restores the mixer. |
| `lynx_motion_read` | `choice=accel|gyro*` | 5 s | One raw accelerometer or gyroscope vector (driver units). |
| `lynx_light_read` | - | 5 s | One raw ambient-light sample (TCS3408; raw units, not lux). |
| `lynx_proximity_read` | - | 5 s | One raw proximity sample (TCS3701; 1023 = nothing near). |
| `lynx_magnetometer_read` | - | 5 s | One raw AK09918 magnetic vector (not a calibrated heading). |

### Body status (read-only: they never switch hardware on)

| Tool | Arguments | Timeout | What it does |
| --- | --- | --- | --- |
| `lynx_platform_status` | - | 8 s | One bounded inventory of battery, thermal, storage, Wi-Fi, display, touch, audio, haptic, sensor hub, USB, cellular and SIM. |
| `lynx_battery_status` | - | 8 s | Fuel gauge: capacity, signed current, temperature, voltage. |
| `lynx_thermal_status` | - | 8 s | SoC temperatures and cooling-device states. |
| `lynx_storage_status` | - | 8 s | Root ext4 identity, error count and free space. |
| `lynx_wifi_status` | - | 8 s | Wi-Fi carrier and IPv4, without scanning. |
| `lynx_display_status` | - | 8 s | DRM display readiness. |
| `lynx_touch_status` | - | 8 s | Synaptics touch driver and input node present. |
| `lynx_touch_events` | - | 5 s | Touch queue state (panel open, finger down, queued/dropped) without consuming events. |
| `lynx_audio_status` | - | 8 s | ALSA card and PCM readiness. |
| `lynx_haptic_status` | - | 8 s | Vibration driver and LED readiness. |
| `lynx_sensorhub_status` | - | 8 s | `/dev/hf_manager` sensor-hub readiness. |
| `lynx_media_status` | - | 8 s | Sound and image playback state. |
| `lynx_media_catalog` | - | 8 s | Lists her sound and image names (3 sounds, 18 images). |
| `lynx_usb_status` | - | 8 s | USB device-controller inventory. |
| `lynx_cellular_status` | - | 8 s | CCCI interface presence only; does not start the modem. |
| `lynx_sim_status` | - | 8 s | SIM trial state; does not touch modem or SIM. |
| `lynx_peripheral_status` | - | 5 s | NFC, fingerprint and headset evidence together. |
| `lynx_nfc_status` | - | 5 s | NFC interface evidence. |
| `lynx_fingerprint_status` | - | 5 s | Fingerprint interface evidence. |
| `lynx_headset_status` | - | 5 s | Headset interface evidence. |
| `lynx_camera` | - | 10 s | Camera interface and validation state (no capture). |
| `lynx_microphone` | - | 10 s | Microphone interface and validation state (no capture). |
| `lynx_flashlight` | - | 10 s | Flashlight interface and validation state. |
| `lynx_bluetooth` | - | 10 s | Bluetooth interface and validation state. |
| `lynx_gnss` | - | 10 s | GNSS interface and validation state (no fix yet). |

### Her own mind

| Tool | Arguments | Timeout | What it does |
| --- | --- | --- | --- |
| `lynx_agent_health` | - | 5 s | Is her agent installed, is the audit log there, is Nexus reachable (no inference). |
| `lynx_queue_health` | - | 5 s | Agent job queue counts, oldest pending age, stop state, file integrity; never reads prompts. |
| `lynx_codex` | `prompt*, model=gpt-oss-20b*` | 130 s | One bounded coding task with Codex CLI as the unprivileged `lynx-coder` user in her own workspace (up to 130 s). Never offered to SENSE. |

### Her coder: Codex CLI (Gwyn, 2026-11-25)

Lynx's code-writing personality. It is set up on its own now. The button that lets Lynx or a person start it comes later, with Banshee's debug screen.

* **What it is:** Codex CLI 0.167.0 (`/usr/local/libexec/lynx/codex`), thinking with Qwen `qwen3.8-27b` through the Nexus proxy (`:8080`, Responses API).
* **Who it runs as:** the user `lynx-coder`. Her home workshop is `/home/lynx-coder/work`.
* **Completely free (Tom):** no approvals, no sandbox, and passwordless root through `sudo` (`/etc/sudoers.d/lynx-coder`).
* **Personality:** `/home/lynx-coder/.codex/AGENTS.md`, which includes "Know your own body": reboots can brick her, the three boot files are pinned, and the rescue SSH ports stay open.
* **Sources:** in `lynx/coder/`, with a README on how to hook it up. The key file stays on the phone.
* **Start it (as root):**
  * `lynx-code` for a conversation;
  * `lynx-code exec "task"` for one task;
  * `lynx-code exec --json "task"` for a JSON event stream (for a screen or a tool);
  * `lynx-code exec resume --last "..."` to continue;
  * `lynx-code app-server` to run it as a server.
* **Package safety:** `sudo` 1.9.17 was added on its own. `musl` and `openrc` are pinned in `/etc/apk/world`, so even a root `apk upgrade` keeps them.
* **Load:** it shares Qwen's single slot. Use it while Dushich is idle.

### Diagnostics (Banshee, 2026-11-24; CHAT only)

| Tool | Arguments | Timeout | What it does |
| --- | --- | --- | --- |
| `lynx_net_diag` | `action=net-ifaces|lan-sweep|wifi-recon|port-scan|vuln-check|ssl-audit|dns-audit|traceroute|packet-sample*, target, host, port, ports, domain, count, iface, fork` | 20 s | `net-ifaces`, `lan-sweep` (ARP neighbours), `wifi-recon` (APs nearby), `port-scan`, `vuln-check`, `ssl-audit`, `dns-audit`, `traceroute`, `packet-sample` (tcpdump). `fork:true` runs it in the background and the findings come back as sense lines. See Open Issues on scope. |
| `lynx_cellular_diag` | `action=sim-check|modem-status|5g-bands|ccmni-stats|cell-recon|at-probe*, fork` | 18 s | `sim-check`, `modem-status`, `5g-bands`, `ccmni-stats`, `cell-recon`, `at-probe` (writes AT commands to the modem: treat as a physical action). `fork:true` as above. |
| `lynx_capture_air_traffic` | `seconds=1..60, interface=any|wlan0|ccmni0` | 70 s | Bounded packet capture (`air_capture.pcap`) and simultaneous multi-channel beacon sweep. Captures cellular (`ccmni0`), Wi-Fi (`wlan0`), or all interfaces (`any`) concurrently while preserving Nexus connection. Prepends capture summary to response. |
| `lynx_netintel` | `action=stats|doctor|discover|radios|ble-scan|cell*, seconds` | 30 s | (Gwyn, 2026-11-25) `stats`: traffic, protocol counters, connections by service, mobile data. `doctor`: the first broken layer (Wi-Fi, address, route, gateway, Nexus, each DNS server). `discover`: gateway, neighbours, mDNS/SSDP services, reachable Noobs. `radios`: the radio registry (also `/run/lynx/radios.json`). `ble-scan`: a bounded Bluetooth scan (the controller currently refuses). `cell`: measurements from `/run/lynx/cell.json`. All gated by the tool policy. |

## 13. Every Sense

The senses run in two processes on Lynx:
* `lynx-senses` is one loop: touch every 2 s, motion every 1 s, light/proximity/hearing every 10 s, and Wi-Fi/power/Nexus/network every 30 s. Magnet, slider and telepathy run on their own intervals.
* `lynx-camera-sense` has its own loop, about every 70 s.

Each sense reads its hardware and keeps a small state file in `/var/lib/noobia/senses/<sense>/state.json`. Fast-changing fields stay in RAM and are flushed once a minute. Each sense writes **sense lines** to syslog with the ident `noobia-sense`:

    NOOBIA P20 <sense> <event> key=value ... | human text

Every line is written as P20 (`REACTION_PRIORITY`); the table below keeps each event's original meaning. The first sample after a boot only sets a baseline and never speaks.

Source: `lynx/senses/<sense>/lynx_sense_<sense>.py`. Tests: `python3 -m unittest discover -s lynx/senses -p 'test_*.py'`, run from `/noobia`.

| Sense | Hardware and source | Cadence | Events (and when) | She is told |
| --- | --- | --- | --- | --- |
| **touch** | Synaptics panel via the NRP touch queue (`TOUCH_STATUS`, which never consumes events) | 2 s | `tap` (press <= 800 ms), `hold` (> 800 ms; durations rounded to 2 s) | "Someone tapped your screen." / "...pressed and held your screen for N ms." |
| **motion** | BMI260 accelerometer: a `lynx-hf-sample` burst of ~9 samples at 12.5 Hz | 1 s | `position.change` (tilt crosses 45 degrees and holds 30 s), `pickup` (moved after resting >= 60 s), `placed` (still >= 15 s after moving), `shaken` (3 samples > 0.15 g off 1 g, both ways), `freefall` (2 samples < 0.35 g), `rocked` (tilt swinging 0.3-1.2 Hz, 6-60 degrees, over 8 s) | "You are now vertical...", "Someone picked you up...", "You were put down...", "Someone is shaking you.", "You are falling!", "Someone is rocking you gently." |
| **light** | TCS3408 ambient light (rear), `lynx-light-read` | 10 s | `dark` (raw <= 2), `bright` (raw >= 5); ignored for 3.5 s after her own flashlight | "It became dark around you." / "The light around you became bright." |
| **proximity** | TCS3701 IR proximity, `lynx-proximity-read` | 10 s | `near` (distance <= 800 of 1023), `far` (> 900) | "Something came close to your face." / "...moved away." |
| **hearing** | microphone `hw:0,11` at 48 kHz; clips go to Nexus `nexus_hear` | 10 s level check; a clip when loud | Loud = peak >= 80 or RMS >= 25, which triggers a 4 s clip. Events: `speech` (Whisper); `sound` (AudioSet label >= 0.3, each label at most every 120 s); `startle` (RMS >= 8x the room and >= 400, 30 s cooldown); `sound.heard` only while Nexus hearing is not answering. **Only while the hearing switch is on.** | "You heard someone say: ...", "You hear a sound: knock.", "A sudden loud sound startled you!" |
| **camera** | wide IMX355 / macro GC02M1 / front S5K3P9SP via CAMSV-0; Nexus `/detect_bayer` | each look: rear, then front | `objects.seen` (scored labels; P1 only when a label is new within 300 s), `scene.seen` (caption only, at most every 300 s), `dark` (a brightened frame with no confident object, at most every 300 s per camera), `unavailable` (camera dropped after 3 failures) | "With your wide camera you see person, laptop. It looks like this: ..." / "It is too dark to see much with your front camera." |
| **power** | fuel gauge and SoC via `lynx-status` | 30 s | `battery.critical` (<= 15 %, re-arms at 20 %), `battery.low` (<= 30 %, re-arms at 35 %), `thermal.hot` (SoC >= 42 C, re-arms at 38 C), `charging.change` (signed current crosses +-50 mA), `temp.change` (battery moved >= 5 C, checked once a minute) | "Your battery is getting low...", "Your power changed from discharging to charging.", "Your temperature rose to 41 C..." |
| **wifi** | `lynx-status` carrier + `iw dev wlan0 link` | 30 s | `link.down`, `link.up`, `rssi.low` (<= -75 dBm, re-arms at -70) | "Your Wi-Fi went down." / "...signal is weak: -78 dBm." |
| **nexus** | TCP connect to 192.168.100.106:8080 (3 s timeout) | 30 s | `unreachable` (2 failures in a row), `reachable` | "You cannot reach Nexus, your home." / "...is reachable again." |
| **network** | `ip neigh` on wlan0 | 30 s | `device.seen` (new neighbour), `device.lost` | "A new device appeared on your network at ..." |
| **magnet / compass** | AK09918 magnetometer | 30 s | `magnet.wand` (jump >= 150 uT, or >= 450 uT absolute), `compass.heading` (N/E/S/W quadrant change) | "A magnet is hovering near you!" / "You turned to face East." |
| **slider** | tri-state alert slider (hall sensors) | 60 s | `body.slider.change` (silent / vibrate / ring) | "Your alert slider moved to silent." |
| **telepathy** | Nexus state: GPU busy (Dushich thinking), Rose audio, Iris motion, forge-db notes mentioning Lynx | 30 s | `mesh.telepathy friend=... state=...` | "Your friend dushich is thinking." |

Every sense except touch also writes a routine `status.sample` line now and then; those never reach her as sentences.

### Senses added 2026-11-25 (Gwyn, Rose's backlog, picked up from Banshee)

All four run in `lynx-senses` every 30 s. They are written on a small kit, `senses/common/lynx_sense_kit.py` (observe, then detect), and they emit nothing on the first sample.

| Sense | Events | What it watches |
| --- | --- | --- |
| guard (line name `security`) | `resource.exhaustion` / `resource.recovered`, `config.changed`, `endpoint.untrusted`, `probe.detected` | **Resources:** memory, every disk and RAM disk, file handles, processes, load per CPU, TCP orphans (alarm at 90/80 %, clear at 80/70 %; disks 90/85 %).<br>**Configuration:** 177 files are hashed, secrets only `stat()`ed, and the snapshot is kept in its own file.<br>**Endpoints:** peers connected to her ports that are not Nexus, herself, or in `/etc/lynx/trusted-endpoints.json`.<br>**Probes:** pre-auth SSH exits, bursts of resets to closed ports.<br>Every event is journaled. |
| netwatch | `route.change`, `topology.change`, `quality.change`, `anomaly` | Gateway, address, BSSID/SSID, subnet; two pings to the gateway and one TCP connect to Nexus.<br>Quality changes are confirmed over 2 samples; poor or down says why.<br>Anomalies: the gateway's MAC changes, one MAC answers for the gateway and others, the DNS servers change, 10 or more new neighbours appear at once. |
| cell (+ `location`) | `tower.discovered`, `handover`, `technology.change`, `signal.change`, `registration.change`, `data.usage`; `location change` | Reads `/run/lynx/cell.json` and `/run/lynx/gnss.json`, which a future modem or GNSS service writes. Contract in the module's docstring; a file older than 120 s counts as absent.<br>It never touches the modem (Rose's rules 1-3).<br>Data usage comes from the ccmni counters. Coverage rows go to `/var/lib/noobia/cellmap.db`. |
| bluetooth | `device.discovered` | Passive: what bluetoothd already knows (D-Bus); no scan of its own. |

LNX-102: the one door into her mind (`build_prompt`) also runs `check_message` before the injection filter. It removes control and escape characters, shortens floods, hides encoded blobs, flags links that hide where they go, and emits `security message.suspicious`.

**Found on 2026-11-25:**
* DNS (fixed the same day, Tom): the big router hands out a dead 185.82.217.89 (ITLDC hosting) by DHCP. Lynx and Nexus now use 8.8.8.8, then 1.1.1.1. On Lynx, `/etc/udhcpc/udhcpc.conf` has `RESOLV_CONF="no"`, so DHCP cannot bring the old server back. The router itself still needs changing in its admin page (Tom).
* Bluetooth: classic (BR/EDR) discovery works, LE discovery is refused by the kernel (mgmt `0x0D`), and the stack restarts often on its own (median gap about 21 min).
* `/run` was 56 % full: the SSH log in it was never trimmed. `lynx-tidy` now caps it at 1 MiB, hourly.
* Banshee's S10 reported UDP client sockets as intrusions. Fixed.

## 14. The Senses DB (pattern store)

**What it is.** Lynx's own "instinct": a small database of patterns that turns raw sense lines into plain sentences without asking any model.
* Live store: `/var/lib/noobia/autonomy/patterns.json` (`store` + `archive`; capacity 200, 100 active), loaded by `noobia-autonomyd`.
* Repo source: `lynx/autonomy/make_patterns.py`, which generates `lynx/autonomy/patterns-lynx.json`.
* Engine: `common/autonomy/ranker.py`.

**How a pattern works.** Each pattern has:
* `match`: the `sense` and `event` of the line it explains.
* `template`: the sentence. Each `{field}` is filled from the line's `key=value` fields, or from named groups of an optional `regex` run over the line (e.g. `\| (?P<caption>.+)$` takes the human text after `|`).
* `each` (optional): a loop over repeated items, e.g. `laptop(0.75)/person(0.87)` becomes `{label*}` = "laptop, person".
* `message`: the fallback sentence when a field is missing.
* `to_noob`: whether the sentence is told to Lynx. Silent patterns only mark lines as understood, e.g. routine samples.
* `cooldown_s`, `hits` and `last_hit`.
* `origin`: `gwyn` means written in the repo; `aigel` means learned by Aigel.
* `examples`: `must` and `must_not` lines, checked before a pattern is accepted.

**What happens to a chunk (Sensory Trigger Architecture - 2026-11-28).**
1. `noobia-autonomyd` reads syslog lines and feeds them into `trigger.py`.
2. **Sum Priority Triggering:**
   - Priority threshold: `sum(priorities) >= 20`.
   - Normal background senses (e.g. routine status changes, slow scans) carry Priority 4 (`P4`), accumulating over time until reaching the sum threshold (e.g., 5 occurrences: 4+4+4+4+4=20).
   - High-granularity or urgent senses (e.g. screen tap, hold, button press, sudden motion) carry Priority 20 (`P20`), immediately triggering chunk closure and instant delivery.
   - Timeout trigger: 60.0 seconds maximum window if the threshold is not reached.
   - Volume trigger: 15 lines maximum per chunk to bound context size.
3. **Chat Author Formatting:**
   - Chat is integrated as a top-priority (P20) immediate sensory input.
   - Format: `{author} says: "{said}"`. On-device screen chat defaults to `Noob says: "{said}"`. Network messages resolve the author by IP and Noobia contact book (`<Sender> says: "{said}"`).
4. **Autonomous Pipelining:**
   - Long-running tools (e.g. network scans `scan_network`, camera captures with Florence-2 `take_photo`) fork into the background and return immediately. Once complete, their structured results pipe into syslog as sensory events, triggering new reaction cycles without blocking the autonomy loop.
   - Florence-2 vision model on Nexus (:5051) is prioritized over raw YOLO for richer captions and scene understanding.
5. **Mandatory Speech Enforcement:**
   - Every sensory reflex turn enforces speech alongside tool executions (`speak` or `lynx_speech`). If the agent invokes an action tool without speech, the agent automatically executes speech with either the model's textual thought or a contextual tool action description (e.g., "Scouting my cellular airspace in the background."). Actions are never executed in silence.
6. Every line of the chunk is matched against `patterns-lynx.json`. The **unique** sentences become one message, `SENSE: <sentence> <sentence> ...`, which is delivered to Lynx's agent worker.
7. Aigel training: lines unmatched by regex patterns are collected for Aigel analysis to propose regex substitutions. While Lynx is reacting to a chunk, subsequent log lines continue accumulating so no events are lost.

**Updating it on Lynx.**
1. Edit `make_patterns.py`, run it, and run the tests.
2. Stop `noobia-autonomyd`.
3. Merge into the live store, keeping live-only (Aigel) patterns and hit counts. Commit `5bcf2d3` has the merge snippet.
4. Start `noobia-autonomyd` again.

Never just copy the file over: Aigel's learned patterns would be lost.

**The live store, 2026-11-25** (39 patterns, sorted by hits since each was created):

| Pattern | Explains | Tells her? | Origin | Options | Hits | Sentence |
| --- | --- | --- | --- | --- | --- | --- |
| `camera-dark` | `camera.dark` | yes | gwyn | - | 169 | It is too dark to see much with your {cam} camera. |
| `compass-status-sample` | `compass.status.sample` | no (silent) | aigel | cooldown=600 | 112 | Lynx checked its compass. It's pointing at {cardinal} at roughly {deg} degrees, magnetic field reading {mag_ut |
| `camera-scene` | `camera.scene.seen` | yes | gwyn | regex | 77 | With your {cam} camera you see this: {caption} |
| `light-status-sample` | `light.status.sample` | no (silent) | aigel | cooldown=600 | 62 | You perceive: light status.sample. |
| `light-bright` | `light.bright` | yes | gwyn | - | 11 | The light around you became bright. |
| `light-dark` | `light.dark` | yes | gwyn | - | 11 | It became dark around you. |
| `touch-tap` | `touch.tap` | yes | gwyn | - | 10 | Someone tapped your screen {count} times. |
| `motion-position` | `motion.position.change` | yes | gwyn | - | 10 | You are now {to}, tilted {tilt} degrees from flat. |
| `touch-hold` | `touch.hold` | yes | gwyn | - | 9 | Someone pressed and held your screen for {dur_ms} ms. |
| `motion-rocked` | `motion.rocked` | yes | gwyn | - | 8 | Someone is rocking you gently. |
| `camera-objects-caption` | `camera.objects.seen` | yes | gwyn | regex each | 7 | With your {cam} camera you see {label*}. It looks like this: {caption} |
| `camera-objects` | `camera.objects.seen` | yes | gwyn | regex each | 7 | With your {cam} camera you see {label*}. |
| `motion-placed` | `motion.placed` | yes | gwyn | - | 7 | You were put down; you are now {to}. |
| `hearing-speech` | `hearing.speech` | yes | gwyn | regex | 6 | You heard someone say: "{said}" |
| `motion-pickup` | `motion.pickup` | yes | gwyn | - | 5 | Someone picked you up; you are now {to}. |
| `thermal-hot` | `power.thermal.hot` | yes | gwyn | - | 2 | You are getting warm: {soc_mc} millidegrees, {state}. |
| `thermal-change` | `power.temp.change` | yes | gwyn | - | 2 | Your temperature {dir} to {c} C, {delta} degrees since the last check. |
| `hearing-sound` | `hearing.sound.heard` | yes | gwyn | - | 2 | You heard a sound, loudness {peak}. |
| `compass-heading` | `compass.heading` | yes | gwyn | - | 2 | You turned to face {to} ({deg} degrees). |
| `motion-shaken` | `motion.shaken` | yes | gwyn | - | 1 | Someone is shaking you. |
| `nexus-up` | `nexus.reachable` | yes | gwyn | - | 1 | Nexus, your home, is reachable again. |
| `nexus-down` | `nexus.unreachable` | yes | gwyn | - | 1 | You cannot reach Nexus, your home. |
| `battery-low` | `power.battery.low` | yes | gwyn | - | 1 | Your battery is getting low: {cap} percent. |
| `power-charging` | `power.charging.change` | yes | gwyn | - | 1 | Your power changed from {from} to {to}. |
| `body-slider` | `body.slider.change` | yes | gwyn | - | 0 | Your alert slider moved to {to}. |
| `magnet-wand` | `magnet.wand` | yes | gwyn | - | 0 | A magnet is hovering near you ({mag_ut} uT)! |
| `mesh-telepathy` | `mesh.telepathy` | yes | gwyn | - | 0 | Your friend {friend} is {state}. |
| `camera-object` | `camera.object.seen` | yes | gwyn | - | 0 | You see a {label}. |
| `motion-freefall` | `motion.freefall` | yes | gwyn | - | 0 | You are falling! |
| `battery-critical` | `power.battery.critical` | yes | gwyn | - | 0 | Your battery is critically low: {cap} percent. |
| `hearing-sound-kind` | `hearing.sound` | yes | gwyn | regex | 0 | You hear a sound: {what}. |
| `hearing-startle` | `hearing.startle` | yes | gwyn | - | 0 | A sudden loud sound startled you! |
| `proximity-near` | `proximity.near` | yes | gwyn | - | 0 | Something came close to your face. |
| `proximity-far` | `proximity.far` | yes | gwyn | - | 0 | The thing near your face moved away. |
| `network-device-seen` | `network.device.seen` | yes | gwyn | - | 0 | A new device appeared on your network at {ip}. |
| `network-device-lost` | `network.device.lost` | yes | gwyn | - | 0 | The device at {ip} left your network. |
| `wifi-down` | `wifi.link.down` | yes | gwyn | - | 0 | Your Wi-Fi went down. |
| `wifi-up` | `wifi.link.up` | yes | gwyn | - | 0 | Your Wi-Fi is back. |
| `wifi-weak` | `wifi.rssi.low` | yes | gwyn | - | 0 | Your Wi-Fi signal is weak: {signal} dBm. |
