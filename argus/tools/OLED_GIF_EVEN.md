# `oled_gif_even`

Minimal native Argus tool for the experimental GME128128/SH1107 panel.
It decodes the first GIF frame with `stb_image`, resizes it to 128×128 by
nearest-neighbour sampling, and writes it over `/dev/i2c-1` at address `0x3c`.

This tool encodes the behavior we measured on the current wiring:

- RAM column 0 is the visible horizontal center, so X is shifted by 64.
- RAM bit 0 is unreliable; image rows are shifted down one RAM bit and the
  bottom source row is clipped.
- Every transmitted RAM byte is masked with `0xfe`.
- It is a first-frame renderer; animation timing is intentionally omitted.

Build on Argus:

```sh
cc -O2 -I. -o oled_gif_even oled_gif_even.c -lm
```

Run with Argon's I²C service stopped so the power controller does not contend:

```sh
sudo systemctl stop argononed.service
./oled_gif_even image.gif
sudo systemctl start argononed.service
```

The source requires `vendor/stb_image.h`.
