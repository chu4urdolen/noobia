# Rose on Syra — 2026-10-07

- Backend: user `rose-chat.service`, OpenAI Responses API, configurable default
  `gpt-5.4-mini`; key is private in `~/.config/rose-chat/settings.json` on Syra.
- Microphone: ReSpeaker English Whisper, Nexus preferred with local Syra fallback;
  collection is enabled by default. Capture/VAD remains on Syra; a warm Nexus
  worker decodes phrases through a persistent pinned SSH connection. A dedicated
  key permits only the transcription bridge. Retry cooldown is 10 seconds after
  failure; the same phrase waits for the single local decode slot. Transcript
  events name the worker and chunk ID. Scheduler prioritizes free Nexus, then
  Syra, then optional Argus; one job per worker. Pending chunks are assigned
  only at dispatch, and completed results are released in capture order.
  Argus is offline and its slot disabled; Nexus setup script is prepared at
  `/noobia/speech_to_text/setup_argus_worker.py`. It has not been installed on
  Argus or verified on that hardware.
  All finalized phrases accumulate until the latest contains the whole word
  `love`. Microphone control is an explicit tool. Closing GUI does not stop it.
- GUI: black with green panel borders; keyboard/input history/spoken replies/
  raw tool text on touchscreen DSI-2. Camera images fit a separate fullscreen
  HDMI-A-2 window. XDG autostart starts `rose-chat-gui.service` at desktop login.
- Tools: `rose_`, `syra_`, `lolth_` prefixes identify the entity. Descriptions
  come directly from each shell wrapper's `--help`; manifests validate arguments.
  Projector wrapper is archived outside active discovery. Full shell access
  runs as the `rose` user.
- 30 active tools; one `rose_camera` captures and detects objects. Its live test
  returned a photo and detection metadata. Default speech/light tool events are
  hidden from the tool panel. Replies favor shorter natural speech; punctuation
  other than `. , ! ?` is replaced with spaces before GUI and speech output.
- YouTube: official search key configured privately; official Extra Terra video
  `0t_I5IdYGBg` verified playing unmuted on HDMI. Nonblocking embedded playback
  supports pause/resume/volume/mute/seek/stop. Account sign-in still needs Noob
  once through the native browser sign-in button. Dedicated browser profile
  avoids keyring prompts and disables password saving.
- Recovery: capture supervisor reacquires the ReSpeaker, device watcher restores
  paired JBL audio, and media service supervises Chromium with playback position
  checkpoints. Adapter profiles use stable hardware identities. TP-Link, GNSS
  and Ubertooth removed: specialized wrappers archived and monitoring updated.
- Credentials: both API keys remain only in private Syra settings (0600), outside
  the repository. Candidate Git files scanned without printing secrets: zero API
  key matches. Nothing committed or pushed during this setup.
- Display freeze repair: restarted only the media service. Added player
  heartbeat supervision for living browsers with frozen renderers; track changes
  no longer navigate the whole page. Temporary loading/pause events no longer
  overwrite the requested autoplay setting. Live video progress and pause/resume
  verified after repair; chatbot and microphone services remain running.
- Play now replaces the current video directly, with autoplay enabled and no
  video queue. Tool success requires actual playback of the requested video;
  startup errors return within 20 seconds. Playback continues after tool return.
- New videos start at 50% volume. Chromium placement waits for labwc to apply
  the HDMI move before entering fullscreen; restart placement was verified at
  HDMI-A-2 coordinates 2464,0 with dimensions 1920x1080.
- Nexus transcription verification: reference audio, same-phrase Syra fallback
  and return to Nexus tested. Warm six-second phrases took 1.49–2.23 seconds
  including transport, with about 0.42 seconds of Nexus decoding. WiFi latency
  varies; offloading is not always faster for larger recordings. No cloud STT.
- Lolth: LAFVIN Spiderbot, Robot - EC36 AP, HTTP 192.168.4.1. COMFAST USB
  0bda:d723, MAC 40:a5:ef:70:7d:cb, currently wlan1, driver rtw88_8723du.
  NetworkManager profile `Lolth COMFAST` binds the MAC, auto-connects, and never
  supplies a default route or DNS. The AP was absent during installation.
  Eleven client tools are installed; no movement commands were tested.
- Syra primary network remains Noobia on wlan0. TP-Link USB is currently wlan2.
- Nexus-side `/noobia/aria/syra-shutdown` sends graceful SSH poweroff, waits
  300 seconds, then cuts Tuya only if the generation remains valid and Syra is
  offline. `/noobia/aria/syra-start` revokes pending cuts before ON under a shared
  lock. Real operations are blocked until the Tuya local key is supplied.
- Root setup on Syra backed up to
  `/var/backups/noobia-rose-agent-20261006-232428/`.
