/* Native, dependency-light image -> 128x128 1-bit GIF converter. */
#define STB_IMAGE_IMPLEMENTATION
#include "vendor/stb_image.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static void put_code(uint8_t *out, size_t *bit, unsigned code)
{
  for (unsigned i = 0; i < 3; ++i) {
    if (code & (1u << i)) out[*bit >> 3] |= (uint8_t)(1u << (*bit & 7));
    ++*bit;
  }
}

int main(int argc, char **argv)
{
  if (argc != 3) {
    fprintf(stderr, "usage: %s input-image output.gif\n", argv[0]);
    return 2;
  }
  int w, h, channels;
  unsigned char *src = stbi_load(argv[1], &w, &h, &channels, 1);
  if (!src) { fprintf(stderr, "decode failed: %s\n", stbi_failure_reason()); return 1; }

  /* Each pixel is emitted as clear-code, palette-index. This is deliberately
     simple rather than compact, and keeps the GIF encoder tiny and robust. */
  uint8_t codes[20000] = {0};
  size_t bit = 0;
  for (int y = 0; y < 128; ++y) {
    int sy = (y * h) / 128;
    for (int x = 0; x < 128; ++x) {
      int sx = (x * w) / 128;
      unsigned pixel = src[sy * w + sx] >= 128 ? 1u : 0u;
      put_code(codes, &bit, 4);       /* clear dictionary */
      put_code(codes, &bit, pixel);
    }
  }
  put_code(codes, &bit, 5);           /* end of information */
  size_t code_bytes = (bit + 7) / 8;

  FILE *f = fopen(argv[2], "wb");
  if (!f) { perror(argv[2]); stbi_image_free(src); return 1; }
  fwrite("GIF89a", 1, 6, f);
  fputc(128, f); fputc(0, f);         /* 128x128 logical screen */
  fputc(128, f); fputc(0, f);
  fputc(0xF0, f); fputc(0, f); fputc(0, f); /* 2-entry global palette */
  fputc(0, f); fputc(0, f); fputc(0, f); /* black */
  fputc(255, f); fputc(255, f); fputc(255, f); /* white */
  fputc(',', f); fputc(0, f); fputc(0, f); fputc(0, f); fputc(0, f);
  fputc(128, f); fputc(0, f); fputc(128, f); fputc(0, f); fputc(0, f);
  fputc(2, f);                          /* minimum LZW code size */
  for (size_t pos = 0; pos < code_bytes;) {
    size_t n = code_bytes - pos; if (n > 255) n = 255;
    fputc((int)n, f); fwrite(codes + pos, 1, n, f); pos += n;
  }
  fputc(0, f); fputc(';', f);
  fclose(f); stbi_image_free(src);
  printf("wrote %s (128x128, 1-bit, %zu-byte image stream)\n", argv[2], code_bytes);
  return 0;
}
