#!/usr/bin/env python3
"""Offline analysis foundation. Heavy models are optional, imported on demand."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import math
from pathlib import Path
import re
import statistics
import wave
from dataclasses import dataclass


def finite(value, name):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def inspect_audio(path):
    with wave.open(str(path), "rb") as audio:
        if audio.getnchannels() not in (1, 2) or audio.getcomptype() != "NONE":
            raise ValueError(f"{path}: use mono or stereo integer PCM WAV")
        if audio.getsampwidth() not in (1, 2, 3, 4) or not audio.getnframes():
            raise ValueError(f"{path}: unsupported or empty WAV")
        return {"sample_rate": audio.getframerate(), "channels": audio.getnchannels(),
                "frames": audio.getnframes(), "duration_s": audio.getnframes() / audio.getframerate()}


def make_grid(spec, duration, mix, base):
    divisions = spec.get("subdivisions_per_beat", 4)
    if isinstance(divisions, bool) or not isinstance(divisions, int) or not 1 <= divisions <= 64:
        raise ValueError("subdivisions_per_beat must be an integer from 1 to 64")
    mode = spec.get("mode", "manual")
    if mode == "manual":
        bpm = finite(spec["bpm"], "bpm")
        offset = finite(spec.get("offset_s", 0), "offset_s")
        if not 0 < bpm <= 1000 or not 0 <= offset < duration:
            raise ValueError("manual BPM must be in (0,1000]; offset must be inside the song")
        step = 60 / bpm
        beats = [offset + i * step for i in range(math.ceil((duration - offset) / step))]
    elif mode == "json":
        beats = json.loads((base / spec["path"]).read_text())["beat_times_s"]
    elif mode == "beat_this":
        from beat_this.inference import File2Beats
        tracker = File2Beats(checkpoint_path=spec.get("model", "final0"),
                             device=spec.get("device", "cpu"), dbn=False)
        detected, _downbeats = tracker(str(mix))
        beats = [float(t) for t in detected]
    else:
        raise ValueError(f"Unknown grid mode: {mode}")
    beats = [finite(t, "beat time") for t in beats]
    if not beats or any(t < 0 or t >= duration for t in beats):
        raise ValueError("Beat times must lie within the song")
    if any(b <= a for a, b in zip(beats, beats[1:])):
        raise ValueError("Beat times must increase strictly")
    if mode != "manual" and len(beats) < 2:
        raise ValueError("Need at least two detected beats; use manual mode for short clips")
    first_step = beats[1] - beats[0] if len(beats) > 1 else step
    last_step = beats[-1] - beats[-2] if len(beats) > 1 else step
    bpm = 60 / statistics.median([b - a for a, b in zip(beats, beats[1:])]) if len(beats) > 1 else bpm
    indexed = [(i, t) for i, t in enumerate(beats)]
    while indexed[0][1] > 0:
        i, t = indexed[0]
        indexed.insert(0, (i - 1, t - first_step))
    while indexed[-1][1] < duration:
        i, t = indexed[-1]
        indexed.append((i + 1, t + last_step))
    grid = []
    for (beat_index, start), (_, end) in zip(indexed, indexed[1:]):
        for sub in range(divisions):
            a = max(0, start + (end - start) * sub / divisions)
            b = min(duration, start + (end - start) * (sub + 1) / divisions)
            if b > a:
                grid.append({"tick": len(grid), "beat_index": beat_index, "subdivision": sub,
                             "start_s": a, "end_s": b,
                             "timing_source": "manual" if mode == "manual" else
                             ("detected" if 0 <= beat_index < len(beats) - 1 else "extrapolated")})
    return bpm, beats, grid


def window_stats(path, grid):
    """Stream disjoint sample windows; preserve both channels without normalization."""
    rows = []
    with wave.open(str(path), "rb") as audio:
        channels, width, rate = audio.getnchannels(), audio.getsampwidth(), audio.getframerate()
        scale = 2 ** (width * 8 - 1)
        for tick in grid:
            start = min(audio.getnframes(), round(tick["start_s"] * rate))
            end = min(audio.getnframes(), round(tick["end_s"] * rate))
            if end <= start:
                raise ValueError("Grid finer than sample rate")
            audio.setpos(start)
            data = audio.readframes(end - start)
            sums = [0.0] * channels
            peak = 0.0
            for offset in range(0, len(data), width):
                raw = data[offset:offset + width]
                sample = ((raw[0] - 128) if width == 1 else int.from_bytes(raw, "little", signed=True)) / scale
                sums[(offset // width) % channels] += sample * sample
                peak = max(peak, abs(sample))
            energy = [s / (end - start) for s in sums]
            left, right = (energy[0], energy[-1])
            rms = math.sqrt(sum(energy) / channels)
            pan_valid = left + right > 1e-12
            rows.append({"rms": rms, "rms_dbfs": max(-120, 20 * math.log10(max(rms, 1e-6))),
                         "peak": peak, "peak_dbfs": max(-120, 20 * math.log10(max(peak, 1e-6))),
                         "pan_pct": 100 * right / (left + right) if pan_valid else "",
                         "left_pct": 100 * left / (left + right) if pan_valid else "",
                         "right_pct": 100 * right / (left + right) if pan_valid else "",
                         "pan_valid": int(pan_valid), "channels": channels})
    return rows


@dataclass
class Context:
    base: Path
    out: Path
    tracks: dict
    grid: list
    stats: dict
    duration: float


def levels(ctx, options):
    fields = ["track", "tick", "start_s", "end_s", "rms", "rms_dbfs", "peak", "peak_dbfs"]
    rows = ({"track": track, **{k: tick[k] for k in ["tick", "start_s", "end_s"]},
             **{k: stat[k] for k in fields[4:]}}
            for track, stats in ctx.stats.items() for tick, stat in zip(ctx.grid, stats))
    write_csv(ctx.out / "levels.csv", fields, rows)
    return ["levels.csv"]


def panning(ctx, options):
    fields = ["track", "tick", "start_s", "end_s", "pan_pct", "left_pct", "right_pct", "pan_valid", "channels"]
    rows = ({"track": track, **{k: tick[k] for k in ["tick", "start_s", "end_s"]},
             **{k: stat[k] for k in fields[4:]}}
            for track, stats in ctx.stats.items() for tick, stat in zip(ctx.grid, stats))
    write_csv(ctx.out / "panning.csv", fields, rows)
    return ["panning.csv"]


def words_json(ctx, options):
    track = options.get("track", "vocals")
    if track not in ctx.tracks:
        raise ValueError(f"Unknown word track: {track}")
    data = json.loads((ctx.base / options["path"]).read_text())
    words = data.get("word_segments")
    if words is None:
        words = [w for segment in data.get("segments", []) for w in segment.get("words", [])]
    if not words:
        raise ValueError("No word records found in JSON")
    rows = []
    for word in words:
        start, end = word.get("start"), word.get("end")
        aligned = start is not None and end is not None
        if aligned:
            start, end = finite(start, "word start"), finite(end, "word end")
            if not 0 <= start <= end <= ctx.duration:
                raise ValueError("Word times outside the song")
        else:
            start = end = ""
        rows.append({"track": track, "start_s": start, "end_s": end, "word": word["word"],
                     "alignment_score": word.get("score", ""), "status": "aligned" if aligned else "unaligned"})
    write_csv(ctx.out / "words.csv", ["track", "start_s", "end_s", "word", "alignment_score", "status"], rows)
    return ["words.csv"]


def midi_notes(ctx, options):
    import mido
    rows = []
    for track, path in options["files"].items():
        if track not in ctx.tracks:
            raise ValueError(f"Unknown MIDI track: {track}")
        midi = mido.MidiFile(ctx.base / path)
        if midi.type == 2:
            raise ValueError("Asynchronous type-2 MIDI requires separate timelines")
        now, active = 0.0, {}
        for msg in midi:  # mido applies tempo changes and converts delta ticks to seconds.
            now += msg.time
            if msg.type not in ("note_on", "note_off"):
                continue
            key = (msg.channel, msg.note)
            if msg.type == "note_on" and msg.velocity:
                active.setdefault(key, []).append((now, msg.velocity))
            elif active.get(key):
                start, velocity = active[key].pop(0)
                if now > ctx.duration + 0.001:
                    raise ValueError("MIDI extends beyond song; verify its timeline")
                drum = msg.channel == 9
                rows.append({"track": track, "start_s": start, "end_s": min(now, ctx.duration),
                             "midi_note": msg.note, "frequency_hz": "" if drum else 440 * 2 ** ((msg.note - 69) / 12),
                             "velocity": velocity, "channel": msg.channel,
                             "event_type": "percussion" if drum else "pitched"})
        if any(active.values()):
            raise ValueError(f"Unclosed MIDI notes in {path}")
    rows.sort(key=lambda r: (r["start_s"], r["track"], r["midi_note"]))
    write_csv(ctx.out / "notes.csv", ["track", "start_s", "end_s", "midi_note", "frequency_hz", "velocity", "channel", "event_type"], rows)
    return ["notes.csv"]


BUILTINS = {"levels": levels, "panning": panning, "words_json": words_json, "midi_notes": midi_notes}


def run(config_path, out):
    config_path = config_path.resolve()
    base = config_path.parent
    config = json.loads(config_path.read_text())
    tracks = {name: (base / path).resolve() for name, path in config["tracks"].items()}
    if "mix" not in tracks or any(not re.fullmatch(r"[a-zA-Z0-9_-]+", n) for n in tracks):
        raise ValueError("Require track 'mix' and simple track IDs")
    metadata = {name: inspect_audio(path) for name, path in tracks.items()}
    duration = metadata["mix"]["duration_s"]
    for name, meta in metadata.items():
        tolerance = max(1 / meta["sample_rate"], 1 / metadata["mix"]["sample_rate"])
        if abs(meta["duration_s"] - duration) > tolerance:
            raise ValueError(f"{name}: duration differs from mix; align stems before analysis")
    bpm, beats, grid = make_grid(config["grid"], duration, tracks["mix"], base)
    enabled = {n: o for n, o in config["analyses"].items() if o.get("enabled", False)}
    plugins = {}
    for name, options in enabled.items():
        if name in BUILTINS:
            plugins[name] = BUILTINS[name]
        else:
            module, function = options["callable"].split(":")
            plugins[name] = getattr(importlib.import_module(module), function)
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)  # A new directory for every experiment.
    manifest = {"schema_version": 1, "song_id": config["song_id"], "status": "running",
                "bpm_median": bpm, "config": config, "tracks": metadata, "analyses": {}}
    try:
        for name, path in tracks.items():
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            metadata[name].update(path=str(path), sha256=digest.hexdigest())
        write_csv(out / "beats.csv", ["beat_index", "time_s", "source"],
                  ({"beat_index": i, "time_s": t, "source": config["grid"].get("mode", "manual")} for i, t in enumerate(beats)))
        write_csv(out / "grid.csv", list(grid[0]), grid)
        stats = {name: window_stats(path, grid) for name, path in tracks.items()} if any(n in enabled for n in ("levels", "panning")) else {}
        ctx = Context(base, out, tracks, grid, stats, duration)
        for name, options in config["analyses"].items():
            if name in enabled:
                manifest["analyses"][name] = {"status": "complete", "outputs": plugins[name](ctx, options)}
            else:
                manifest["analyses"][name] = {"status": "disabled"}
        manifest["status"] = "complete"
    except Exception as exc:
        manifest.update(status="failed", error=str(exc))
        raise
    finally:
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.config, args.out)
    except (ValueError, OSError, KeyError, ImportError, wave.Error) as exc:
        parser.exit(1, f"party: {exc}\n")
    print(f"Analysis complete: {args.out} ({result['bpm_median']:.2f} BPM median)")
