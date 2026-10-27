#!/usr/bin/env python3
"""Convert Lynx PNG poses to compact RGB565 frames for her native display."""

import gzip
import hashlib
import json
from pathlib import Path
import re
import struct

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
PICS = ROOT / "pics"
FRAMES = PICS / "frames"
WIDTH, HEIGHT = 1240, 2772
BAD = "13_dance_180deg.png"


def encode(path: Path) -> bytes:
    with Image.open(path) as image:
        image.load()
        if image.size != (WIDTH, HEIGHT) or image.mode != "RGB":
            raise ValueError(f"unexpected pose format: {path.name}")
        rgb = image.tobytes()
    output = bytearray(WIDTH * HEIGHT * 2)
    for i in range(WIDTH * HEIGHT):
        r, g, b = rgb[3 * i:3 * i + 3]
        value = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        struct.pack_into("<H", output, 2 * i, value)
    return gzip.compress(output, compresslevel=6, mtime=0)


def main():
    source_manifest = json.loads((PICS / "archive-manifest.json").read_text())
    assert source_manifest["excluded"] == BAD
    FRAMES.mkdir(exist_ok=True)
    records = []
    for entry in source_manifest["poses"]:
        src = PICS / entry["file"]
        if src.name == BAD or not re.fullmatch(r"[0-9]{2}_[a-z0-9_]+\.png", src.name):
            raise ValueError(f"bad pose name: {src.name}")
        if hashlib.sha256(src.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"source image changed: {src.name}")
        target = FRAMES / (src.stem + ".rgb565.gz")
        encoded = encode(src)
        if target.exists():
            if target.read_bytes() != encoded:
                raise ValueError(f"converted frame changed: {target.name}")
        else:
            target.write_bytes(encoded)
        records.append({"name": src.stem, "file": target.name,
                        "sha256": hashlib.sha256(encoded).hexdigest(),
                        "bytes": len(encoded)})
    dance = sorted((entry["name"] for entry in records if "_dance_" in entry["name"]),
                   key=lambda name: int(name.rsplit("_", 1)[1].removesuffix("deg")))
    assert len(records) == 17 and len(dance) == 11 and all("180deg" not in n for n in dance)
    (FRAMES / "dance.list").write_text("\n".join(dance) + "\n")
    (FRAMES / "manifest.json").write_text(json.dumps({"width": WIDTH, "height": HEIGHT,
       "format": "little-endian RGB565, gzip compressed", "excluded": BAD,
       "frames": records, "animations": {"dance": {"frames": dance,
       "frame_duration_ms": 500}}}, indent=2) + "\n")
    print(f"Prepared {len(records)} frames and {len(dance)} dance steps")


if __name__ == "__main__":
    main()
