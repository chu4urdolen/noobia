#!/usr/bin/env python3
"""Generate quiet PCM cues for Lynx's initial JSON sound catalog."""

import math
from pathlib import Path
import struct
import wave

OUT = Path(__file__).resolve().parent.parent / "sounds"
RATE = 48000
PEAK = 1400


def cue(name, notes):
    samples = []
    for hz, duration in notes:
        count = round(RATE * duration)
        for n in range(count):
            fade = min(1.0, n / (0.02 * RATE), (count - n) / (0.02 * RATE))
            value = round(PEAK * max(0, fade) *
                          (math.sin(2 * math.pi * hz * n / RATE) if hz else 0))
            samples.append(value)
    OUT.mkdir(exist_ok=True)
    with wave.open(str(OUT / f"{name}.wav"), "wb") as f:
        f.setparams((2, 2, RATE, 0, "NONE", "not compressed"))
        f.writeframes(b"".join(struct.pack("<hh", x, x) for x in samples))


cue("double_beep", [(700, 0.2), (0, 0.12), (700, 0.2)])
cue("chime", [(523.25, 0.22), (659.25, 0.22), (783.99, 0.34)])
