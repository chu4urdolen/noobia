#!/usr/bin/env python3
"""mock_sensory_service.py: Generates random sensory & system log messages for Aigel testing.

Emits a mix of:
1. Known sensory events (already matched in pattern DB)
2. Novel meaningful sensory perceptions (need pattern + status report to Noob)
3. Routine noisy system lines (need pattern with IGNORE=1)
4. System warnings / stress anomalies (feed into Aigel 10-min diagnostic suggestions)
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import random
import sys
import time

NOVEL_PERCEPTIONS = [
    "NOOBIA P1 sensory proximity.approach distance=12cm entity=hand conf=0.88",
    "NOOBIA P1 environmental temperature.drop ambient=18.5C delta=-3.2C",
    "NOOBIA P1 motion vibration.sudden freq=140hz duration=220ms intensity=medium",
    "NOOBIA P1 battery charging.plugged type=fast_usb_pd voltage=9020mv current_ma=1850",
    "NOOBIA P1 hearing voice.whisper text=\"hello little one\" conf=0.91",
    "NOOBIA P1 sensory compass.heading deg=274 dir=west stability=high",
    "NOOBIA P1 camera gesture.wave direction=left_to_right conf=0.82",
    "NOOBIA P1 environmental humidity.rise rh=68% trend=increasing",
]

NOISY_IGNORES = [
    "[sensorhub] sync_poll_tick seq={seq} status=ok latency=0.4ms",
    "[kernel] i2c_bus_idle seq={seq} bus=7 ack=true",
    "NOOBIA P0 power voltage.poll mv=8650 current_ma=-120 state=discharging",
    "[wifi] beacon_probe essid=Noobia_HQ bssid=ac:c0:48:6d:f1:fb rssi=-58 noise=-92",
    "[touch] baseline_recalibration channel=3 drift=0.002 status=nominal",
    "NOOBIA P0 light status.sample raw=0 mode=dark lux=0.1",
    "[timer] heartbeat_tick uptime_sec={seq} load=0.14 cpus_online=8",
    "[pmic] thermal_channel_read ch=1 temp_mc=31200 valid=1",
]

KNOWN_PATTERNS = [
    "NOOBIA P1 touch tap x={x} y={y}",
    "NOOBIA P1 touch hold duration_ms={duration}",
    "NOOBIA P1 hearing sound.heard peak={peak} rms={rms}",
    "NOOBIA P1 camera object.seen label=cat conf=0.92",
    "NOOBIA P1 light bright lux=850 state=sunny",
]

ANOMALIES_AND_WARNINGS = [
    "[touch] buffer_warning dropped_events=42 queue_overflow=1 latency_ms=180",
    "[thermal] zone soc_mc=52500 state=elevated throttle=soft_active",
    "[power] battery_reserve_low capacity=14% voltage_mv=7200 current_ma=-850",
    "[sensorhub] i2c_timeout bus=7 retry_count=3 recovered=true",
    "[agent] cognitive_queue_backlog size=4 max_allowed=1 dropping_stale=true",
]


def generate_line(seq: int) -> tuple[str, str]:
    """Generate one line. Returns (category, formatted_line)."""
    roll = random.random()
    now_str = datetime.now(timezone.utc).strftime("%b %d %H:%M:%S")

    if roll < 0.35:
        # 35% chance: Noisy routine line (should be ignored)
        tmpl = random.choice(NOISY_IGNORES)
        line = tmpl.format(seq=seq)
        cat = "NOISY_IGNORE"
    elif roll < 0.65:
        # 30% chance: Known pattern
        tmpl = random.choice(KNOWN_PATTERNS)
        line = tmpl.format(
            x=random.randint(100, 1100),
            y=random.randint(200, 2400),
            duration=random.randint(500, 3000),
            peak=random.randint(80, 250),
            rms=f"{random.uniform(15.0, 60.0):.1f}",
        )
        cat = "KNOWN"
    elif roll < 0.85:
        # 20% chance: Novel perception
        line = random.choice(NOVEL_PERCEPTIONS)
        cat = "NOVEL_PERCEPTION"
    else:
        # 15% chance: System warning / anomaly
        line = random.choice(ANOMALIES_AND_WARNINGS)
        cat = "ANOMALY_WARNING"

    full_line = f"{now_str} nexus-test daemon.notice: {line}"
    return cat, full_line


def main():
    parser = argparse.ArgumentParser(description="Mock sensory log emitter for Aigel")
    parser.add_argument("--output", "-o", default=None, help="Output file path (default: stdout)")
    parser.add_argument("--count", "-n", type=int, default=0, help="Number of messages to emit (0 = forever)")
    parser.add_argument("--min-interval", type=float, default=0.2, help="Min delay between lines (sec)")
    parser.add_argument("--max-interval", type=float, default=1.0, help="Max delay between lines (sec)")
    args = parser.parse_args()

    out_file = None
    if args.output:
        p = Path(args.output)
        p.parent.mkdir(parents=True, exist_ok=True)
        out_file = open(p, "a", encoding="utf-8")

    seq = 1000
    count = 0
    try:
        while True:
            seq += 1
            count += 1
            cat, line = generate_line(seq)
            if out_file:
                out_file.write(line + "\n")
                out_file.flush()
            else:
                print(f"[{cat}] {line}", flush=True)

            if args.count > 0 and count >= args.count:
                break

            time.sleep(random.uniform(args.min_interval, args.max_interval))
    except KeyboardInterrupt:
        pass
    finally:
        if out_file:
            out_file.close()


if __name__ == "__main__":
    main()
