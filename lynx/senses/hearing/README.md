# Lynx Hearing Sense (S9)

The hearing sense provides acoustic perception for Lynx through her onboard microphone hardware, level sampling, and local Nexus Whisper STT (`http://192.168.100.106:5052/hear`).

## Spam & Audio Noise Guard: Disabled by Default

Hearing is **disabled by default**. This intentional policy prevents Lynx from:
1. Being spammed with continuous background room noise or ambient chatter.
2. Triggering repetitive, unsolicited audio processing and model inference.

## Enabling / Disabling Hearing

Hearing can be dynamically toggled via two methods:

1. **Nexus Web UI / API Button:**
   - Endpoint: `http://192.168.100.106:112/api/v1/hearing`
   - Returns: `{"enabled": true}` or `{"enabled": false}`
   - The user (Noob/Tom) can toggle hearing on and off via the Nexus dashboard button.
2. **Local Override File:**
   - Path: `/var/lib/noobia/senses/hearing/enabled`
   - Content: `1` (enabled) or `0` (disabled).
   - If present, this overrides the Nexus API.

When hearing is disabled, `lynx_sense_hearing.py` exits immediately with `{"ok": true, "enabled": false, "emitted": []}`, performing zero microphone sampling and capturing no audio clips.

## How Hearing Operates (When Enabled)

1. **Microphone Sampling (`FAST_SAMPLE_EVERY_S = 10.0`):**
   - Sampled by `lynx_senses_loop.py` every 10 seconds using `lynx_microphone_level.sh`.
   - Baseline ambient room RMS is continuously tracked (`quiet_rms`).
2. **Dynamic Audio Clip Capture:**
   - If `peak >= 80` or `rms >= 25.0` (or `STARTLE_RATIO >= 8.0` over baseline ambient), a detached background thread records a 4-second PCM clip (`lynx_microphone_clip.py`).
   - The raw PCM buffer is sent directly to Nexus port 5052 for AudioSet class tagging and Whisper speech-to-text.
   - The raw audio clip is held only in memory during the request and immediately deleted.
3. **Sensory Output:**
   - Emits `NOOBIA P20 hearing speech lang=... | <text>` or `NOOBIA P20 hearing sound | <label>` into syslog (`noobia-sense`).
   - Senses chunker and ranker package the observation into `SENSE:` prompt for Qwen.
   - Lynx reacts vocally and can spontaneously launch diagnostics (`lynx_net_diag`, `lynx_cellular_diag`).
