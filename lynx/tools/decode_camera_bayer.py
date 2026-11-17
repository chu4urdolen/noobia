#!/usr/bin/env python3
"""Turn a Lynx CAMSV Bayer frame into viewable PNGs and pixel statistics."""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageOps
from camera_frame_quality import frame_quality
from preview_lut import make_lut

WIDTH = 1600
HEIGHT = 1200


def planes(raw, phase="rggb", width=WIDTH, height=HEIGHT):
    top_left = bytearray()
    green_top = bytearray()
    green_bottom = bytearray()
    bottom_right = bytearray()
    for y in range(0, height, 2):
        top = raw[y * width:(y + 1) * width]
        bottom = raw[(y + 1) * width:(y + 2) * width]
        top_left.extend(top[::2])
        green_top.extend(top[1::2])
        green_bottom.extend(bottom[::2])
        bottom_right.extend(bottom[1::2])
    size = (width // 2, height // 2)
    red, blue = ((bottom_right, top_left) if phase == "bggr"
                 else (top_left, bottom_right))
    return [Image.frombytes("L", size, bytes(channel))
            for channel in (red, green_top, green_bottom, blue)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--sensor", type=int, choices=(2, 4), default=4)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--bayer-phase", choices=("bggr", "rggb"), default="rggb",
                        help="interpret top-left pixel; sensor source, live seninf, and color target favor RGGB")
    parser.add_argument("--black-level", type=int, default=16,
                        help="preview-only black offset; raw file is unchanged")
    parser.add_argument("--preview-gain", type=float, default=3.0,
                        help="preview-only linear brightness gain")
    parser.add_argument("--preview-gamma", type=float, default=1.8,
                        help="preview-only display gamma")
    args = parser.parse_args()
    expected_mode = {4: (1600, 1200), 2: (3264, 2448)}[args.sensor]
    args.width = args.width if args.width is not None else expected_mode[0]
    args.height = args.height if args.height is not None else expected_mode[1]
    if (args.width, args.height) != expected_mode:
        parser.error("dimensions must match the selected sensor's reviewed mode")
    if (args.width < 2 or args.height < 2 or args.width % 2 or args.height % 2 or
            args.width * args.height > 32 * 1024 * 1024):
        parser.error("Bayer dimensions must be positive even values within 32 MiB")
    raw = args.raw.read_bytes()
    expected = args.width * args.height
    if len(raw) != expected:
        raise RuntimeError(f"expected {expected} bytes, got {len(raw)}")
    output = args.output_dir or args.raw.parent
    output.mkdir(parents=True, exist_ok=True)
    prefix = f"sensor{args.sensor}"
    gray = Image.frombytes("L", (args.width, args.height), raw)
    gray_path = output / f"{prefix}-mosaic-gray.png"
    gray.save(gray_path)
    red, green_top, green_bottom, blue = planes(raw, args.bayer_phase,
                                               args.width, args.height)
    green = ImageChops.add(green_top, green_bottom, scale=2)
    rgb = Image.merge("RGB", tuple(channel.resize((args.width, args.height), Image.Resampling.BILINEAR)
                                    for channel in (red, green, blue)))
    color_path = output / f"{prefix}-preview-rgb.png"
    rgb.save(color_path)
    # Display-oriented view. Dushich's separately tested LUT (commit ceeccc5)
    # lifts the narrow positive signal near black without changing the raw.
    lut = make_lut(args.black_level, args.preview_gain, args.preview_gamma)
    lifted_path = output / f"{prefix}-preview-lifted.png"
    rgb.point(lut * 3).save(lifted_path)
    # Diagnostic only: reveal geometry when the raw 8-bit frame occupies a
    # narrow range near the sensor's black level. This magnifies noise too.
    diagnostic_path = output / f"{prefix}-preview-diagnostic-contrast.png"
    ImageOps.autocontrast(rgb, cutoff=0.5).save(diagnostic_path)
    histogram = gray.histogram()
    dominant_value = max(range(256), key=histogram.__getitem__)
    statistics = {"schema": 1, "source": str(args.raw), "bytes": len(raw),
                  "sensor": args.sensor,
                  "format": f"BA81 payload interpreted as {args.bayer_phase.upper()} 8-bit Bayer",
                  "bayer_phase": args.bayer_phase, "width": args.width, "height": args.height,
                  "min": next(i for i, count in enumerate(histogram) if count),
                  "max": next(i for i in range(255, -1, -1) if histogram[i]),
                  "mean": sum(i * count for i, count in enumerate(histogram)) / len(raw),
                  "unique_values": sum(bool(count) for count in histogram),
                  "dominant_value": dominant_value,
                  "dominant_fraction": histogram[dominant_value] / len(raw),
                  "quality": frame_quality(raw, args.width, args.height, args.black_level),
                  "gray_png": str(gray_path), "rgb_png": str(color_path),
                  "lifted_png": str(lifted_path),
                  "lifted_parameters": {"black_level": args.black_level,
                                        "gain": args.preview_gain,
                                        "gamma": args.preview_gamma},
                  "diagnostic_contrast_png": str(diagnostic_path)}
    (output / f"{prefix}-frame-statistics.json").write_text(json.dumps(statistics, indent=2) + "\n")
    print(json.dumps(statistics, sort_keys=True))


if __name__ == "__main__":
    main()
