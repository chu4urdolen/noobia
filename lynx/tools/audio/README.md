# Lynx Audio Smart Amplifier (NXP TFA9874) Preflight Tool

Read-only offline validator and safe hardware state probe for the dual stereo smart power amplifiers on OnePlus Nord 3.

## Architectural Purpose
Enforces strict boundaries before any attended audio routing trial:
1. Verifies dual stereo amplifier I2C nodes on bus 6 (`6-0034` Left, `6-0035` Right).
2. Verifies reset GPIO routing (`mt6373_pio 2` for Left, `mt6373_pio 1` for Right).
3. Verifies voice coil impedance within nominal limits (5000 to 8000 mΩ).
4. Verifies NXP DSP container firmware assets (`tfa98xx.cnt`).
5. **Strict Acoustic Safety Boundary:** Preflight validates topological readiness without generating audio test tones, without unmuting DACs, and without writing to ALSA PCM streams.

## Usage
- Offline check:
  `python3 lynx_audio_amp_preflight.py`
- Validate fixture:
  `python3 lynx_audio_amp_preflight.py --validate fixtures/audio-amp-ready.json`
- Live read-only check (double-gated):
  `python3 lynx_audio_amp_preflight.py --live --allow-live`
