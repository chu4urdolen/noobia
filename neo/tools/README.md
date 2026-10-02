# Iris photo to monochrome GIF

`iris-photo-gif` is a Linux-side image converter for the NanoPi Neo. It accepts
any format supported by Pillow, makes a square image (128×128 by default),
stretches its useful brightness range, dithers it to true one-bit black and
white, and writes a two-color GIF. The default square crop is suitable for the
GME-128128-01-IIC v2.0 SH1107 panel.

```sh
./iris-photo-gif photo.png
./iris-photo-gif photo.jpg out.gif --size 128 --fit cover
./iris-photo-gif --camera --output iris.bw.gif
```

`--camera` asks Iris for a new JPEG, downloads it from Iris's SD card over the
private USB control link, and converts it. The original JPEG stays on Iris; use
`--keep-camera-jpeg` to also save a local copy beside the GIF. The input form
works with any Pillow-readable picture and does not require Iris to be
connected.

Install the small OS dependency with `sudo apt install python3-pil`. Settings
are in `iris-photo-gif.conf.example`; copy it to
`/etc/noobia/iris-photo-gif.conf`, or use `--config FILE`. CLI flags override
the config. `FIT` may be `cover` (crop to fill), `contain` (letterbox), or
`stretch` (distort to square). `AUTOCONTRAST_CUTOFF` clips that percentile at
each histogram tail before contrast stretch; low-contrast scenes fall back to
their actual extrema. Floyd–Steinberg dithering preserves texture in the
one-bit result.

If a frame is perfectly flat (all pixels identical, usually from complete
clipping), no algorithm can recover scene detail. To honor the black-and-white
output guarantee, the default adds a tiny two-pixel marker in the bottom-right
corner and reports that fallback. Disable it with `ENSURE_BOTH_COLORS=0`.
