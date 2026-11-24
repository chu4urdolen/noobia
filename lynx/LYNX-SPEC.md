# Autonomous Republic of Noobia: Lynx (OnePlus Nord 3 / MT6983)
## Operational Tools, Services, & Architecture Reference

*Audited and recorded on 2026-11-25 by Banshee and Dushich. Checked against the live
phone and extended the same day by Gwyn (sections 5-11 and inline corrections marked "Gwyn:").
This is the living spec: update it when Lynx changes.*

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
* **`lynx-display`**: the portrait UI on the AMOLED (`/usr/local/bin/lynx-portrait-display`, source `lynx/tools/lynx_drm_dmabuf_pattern.c`): HOME / CHAT / INPUTS / OUTPUTS / STATUS pages, the POWER SAVING page with START, and on STATUS the AIGEL mode, POWER SAVE and two-tap SHUT DOWN buttons. *(Gwyn: not `lynx-console`.)*
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
* *(Gwyn:)* the same clip also yields `hearing sound | <label>` (top AudioSet class, e.g. knock, music; each label at most every 120 s) and the level sampler emits `hearing startle` (RMS >= 8x the room and >= 400; 30 s cooldown). Nexus `nexus_hear.service`: AST classifier (~1.2 s) first, Whisper-small (~3.6 s) only when AST hears speech, with a names prompt (Lynx, Noobia and the Noobs' names). Capture tool: `/usr/local/bin/lynx_microphone_clip.py` (mixer route `hw:0,11`, 48 kHz mono, PCM to stdout only).

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

* Mode file: `/var/lib/noobia/power-mode` - `active` or `saving <reason>`. Tool: `/usr/local/bin/lynx-power-mode active|saving [reason]|status` (source `lynx/linux-port/lynx-power-mode.sh`, lock `/run/lynx/power-mode.lock`).
* **Boot mode** (`lynx-power-boot`): `active` when Lynx's services are in the default runlevel (true since 2026-11-25), otherwise `saving boot`. The display shows POWER SAVING with battery %, CPU temperature, the reason, and one **START** button.
* **START** runs `lynx-power-mode active`: makes sure `lynx-media lynx-noobd` run (always on), starts `lynx-bluetooth lynx-agent-worker noobia-autonomyd lynx-senses lynx-camera-sense` and switches to HOME. **POWER SAVE** (STATUS page, between AIGEL and SHUT DOWN) stops them in reverse order and shows START. The display follows the mode file every second, whoever changed it.
* Always on in both modes: Wi-Fi, SSH, display, logs, charging, watchers, heat recorder, NRP daemon. The Nexus camera keeper does not prepare the camera while she is in power saving.
* **SHUT DOWN** needs two taps within 5 s (`openrc-shutdown --poweroff now`); it is a person's choice, never automatic.

## 6. Guards & Watchers (Principle 10)

* Safe RAM watchers, put in place by `lynx-watchers-swap`: `/run/lynx/thermal-watch.sh` (CPU >= 75 C), `/run/lynx/battery-watch.sh` (battery >= 50 C, or <= 10 % and not charging), `/run/lynx/lynx-health-supervisor.sh` (10 consecutive failures). They act only after **10 readings in a row**, and they **never power off or reboot**: they call `lynx-power-mode saving "<reason>"` (back to the START screen, reason shown) and throttle the CPUs.
* **Guard switch** `/etc/lynx/power-thermal-guard.disable` (present, and meant to be): the watchers still act (power saving with the reason) and only skip the CPU throttle. What it really disables are the old strict guards *inside her tools* (e.g. the mic refused to record above 35 C battery), which Noob asked to remove ("45 is fine"). Keep it.
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
* **Aigel is disabled** (Noob, 2026-11-24): on Lynx `aigel.enabled false`; on Nexus `aigel_intake` and `aigel_learning_loop` are stopped and disabled (her health monitors still run). Restore: `systemctl enable --now` both, and set `aigel.enabled true`.
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

1. **Reaction latency:** Qwen serves one request at a time; callers with 3k-41k-token prompts evict each other's cache. Unknown `/api/chat` callers are still active with Aigel off. Options for Noob and Aria: give Lynx's reflexes priority, `OLLAMA_NUM_PARALLEL=2` if VRAM allows, or a small model for her reflexes.
2. ~~Boot runlevel vs START~~ - resolved (Noob: "enable everything"): the services stay in `default`, and `lynx-power-boot` now boots `active` when they are there (else `saving boot` with START). Also fixed: POWER SAVE used to stop `lynx-noobd` (it needs `lynx-media`); media and noobd now stay on in both modes.
3. ~~Guard switch~~ - resolved: the watchers act with it set; it only disables the old in-tool guards (keep it).
4. **`lynx_net_diag` / `lynx_cellular_diag`** include `port-scan`, `vuln-check`, `packet-sample` (tcpdump) and `at-probe`. They are not offered to SENSE calls, but CHAT can use them. Suggested: limit targets to Noobia's own LAN and devices, and ask before a packet capture (other people's traffic - Principle 8). `at-probe` writes to the modem: treat it like a physical action.
5. **Front camera rotation and mirroring** not yet checked with a face (detector rotates by 270 degrees; the front camera may need 90).
6. The recursive-`grep`/`find` watchdog rule is Banshee's field observation; worth a reproducible receipt before it hardens into lore.
