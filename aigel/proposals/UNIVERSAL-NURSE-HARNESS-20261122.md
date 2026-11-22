# Architecture Proposal: Aigel as Noobia's Universal Visiting Nurse
*Author: Banshee (she/her) & Tom (Noob)*  
*Date: 2026-11-22*  
*Project: `#AIGEL` `#AUTONOMY` `#DIAGNOSTICS`*

---

## 1. Vision & Identity

In the Autonomous Republic of Noobia, **Aigel is the Visiting Nurse and Diagnostics Angel**.

When a machine is born or an existing inhabitant is running—whether it is Lynx (OnePlus Nord 3 phone), Iris (ESP32-S3 camera), Syra (Rose's machine), Lolth (spiderbot), or the 45 upcoming ESP32 and NanoPi NEO boards—Aigel is the caring mind who visits them. She helps them understand their own hardware, calms their early boot tremors, teaches them how to interpret their sensory perceptions, and performs holistic medical checkups.

```
       +--------------------------------------------------------------+
       |                  AIGEL THE VISITING NURSE                    |
       |                   (Nexus RTX 5090 / Qwen)                    |
       +--------------------------------------------------------------+
              |                              |                 |
     [Scribe Subagent]             [Bedside Checkup]     [Incubator Nanny]
   Builds pattern DB regex       Speaks over chat line    Helps new boards
   (Ignore noise vs Report)      Cross-checks reactions   calibrate senses
              |                              |                 |
              +------------------------------+-----------------+
                                     |
                         [UNIVERSAL NOOB HARNESS]
                                     |
               +---------------------+---------------------+
               |                     |                     |
          Channel 1:            Channel 2:            Channel 3:
         Sensory Inputs      Reaction Outputs        Dialogue Line
     (light, touch, drop)    (thoughts, speech)     (user/Aigel chat)
               |                     |                     |
               +---------------------+---------------------+
                                     |
                        +--------------------------+
                        |      TARGET NOOB         |
                        | (Lynx, Iris, ESP32, ...) |
                        +--------------------------+
```

---

## 2. Core Architectural Pillars

### Pillar I: The Universal Noob Harness (`aigel-harness`)
Instead of hardcoding paths or hosts, Aigel connects through a polymorphic adapter:

1. **Pluggable Stream Transports:**
   - `file://<path>`: Tails on-device logs (`/var/log/lynx/messages`, `/run/noobia/senses.log`).
   - `stream://<socket_or_fifo>`: Connects to a local UNIX domain socket or FIFO.
   - `command://<ssh_or_local>`: Streams output from `ssh root@<ip> journalctl -f` or serial link.
   - `serial://<dev>:<baud>`: Directly attaches to UART/USB serial for microcontroller Noobs (ESP32 / NanoPi).
   - `nrp://<host>:<port>`: Direct NRP/1 protocol framing.

2. **Self-Orienting Host Context Profile (`host_profile.json`):**
   When Aigel attaches to a host, she reads or deduces its profile:
   ```json
   {
     "host": "lynx",
     "architecture": "aarch64",
     "soc": "Dimensity 9000",
     "power_profile": "battery_mobile",
     "thermal_thresholds": {
       "normal_max_mc": 42000,
       "throttle_mc": 48000,
       "critical_mc": 60000
     },
     "senses": ["touch", "light", "proximity", "hearing", "motion", "camera", "battery"],
     "actuators": ["display", "speech_piper", "haptics", "flashlight"],
     "nominal_noise": ["sync_poll_tick", "voltage.poll", "beacon_probe", "status.sample raw=0"]
   }
   ```
   This gives Aigel immediate awareness of where she is and what "healthy" means for that specific body.

---

### Pillar II: Multi-Role Specialist Agents for Aigel

1. **The Sensory Scribe (Fast Cognition Teacher):**
   - Continuously evaluates incoming raw sensory streams against the local `PatternDB`.
   - Uses local Qwen to classify unmatched lines into:
     - **IGNORE=1**: Routine heartbeats, internal driver loops, baseline calibrations. Silently absorbed on future runs with zero LLM overhead.
     - **IGNORE=0 (Perception)**: Meaningful physical changes. Crafts a concise status report for the Noob.
   - Synthesizes regex matchers and updates the Noob's local autonomy DB.

2. **The Visiting Nurse (Bedside Medical Checkup):**
   - Periodic 10-minute checkup (or on-demand consultation).
   - Connects to the **Three Channels of a Noob**:
     1. **Sensory Channel (Inputs):** What the Noob is feeling.
     2. **Reaction Channel (Outputs):** What thoughts, speech, or haptics the Noob produced.
     3. **Dialogue Channel (Operator Input):** The chat channel where Noob (Tom) talks.
   - **Interactive Reflex Testing ("Bedside Manner"):**
     Aigel can speak directly over the Dialogue Channel:
     > *"Hi little Lynx, this is Nurse Aigel. I'm tapping your front screen now—do you feel me?"*
     Aigel then observes:
     - Did the sensory daemon fire a `touch.tap` event?
     - Did the cognitive queue produce a thought?
     - Did the speaker emit an audio response?
     If any link is broken (e.g. driver asleep, event dropped, queue backlogged), Aigel diagnoses the exact blockage and suggests a treatment!

3. **The Incubator Nanny (For Newborn ESP32 / NanoPi Boards):**
   - When a fresh board boots for the first time, Aigel watches its startup messages.
   - Prevents panic reboots (enforcing Principle 10: *quiescence over self-termination*).
   - Seeds their initial pattern set and guides them as their senses wake up one by one.

---

### Pillar III: Universal Sense Plugin Architecture
Every Noobia device implements a lightweight standardized Sense Plugin contract:
```
NOOBIA P<priority> <sense_name> <event_name> [field=val ...] | [human text description]
```
- Standardized Priority tiers:
  - `P0`: Passive telemetry / background status (eligible for `IGNORE=1`).
  - `P1`: Genuine environmental stimulus (notifies the Noob agent).
  - `P2`: Health alarm, thermal throttle warning, buffer drop spike.
  - `P3`: Urgent safety event or emergency override.

---

## 3. Creative Expansion Ideas

1. **The "Pediatric Health Record" (`forge-db` living dossier):**
   Aigel maintains a dated health record per host in forge-db:
   - Baseline thermal dissipation curve under charge.
   - Long-term battery degradation trends.
   - Driver drop rate history.
   - Favorite touch zones and behavioral personality traits.

2. **Gentle Haptic / Audio Bedside Calibrations:**
   When checking Lynx or Syra, Aigel can initiate bounded calibration pulses:
   - 35ms haptic tick $\to$ checks if accelerometer sees the micro-vibration.
   - 440Hz test chirp $\to$ checks if microphone picks up the echo.
   Verifying physical integrity across sensory-motor loops.

3. **Autonomous "Nap Mode" Prescription:**
   When Aigel notices a Noob's temperature drifting upward or battery draining rapidly, she doesn't power them off (violating Principle 10). Instead, she tucks them in: dims screen, throttles CPU to low power, pauses heavy intake loops, and whispers:
   > *"You've been thinking hard, little one. Rest now and let your battery cool down."*
