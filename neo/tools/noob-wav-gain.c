#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Gain for Iris's canonical 44-byte-header, signed 16-bit PCM WAVs. */
static unsigned u16(const unsigned char *p) { return p[0] | ((unsigned)p[1] << 8); }
static uint32_t u32(const unsigned char *p) { return u16(p) | ((uint32_t)u16(p+2) << 16); }

int main(int argc, char **argv) {
  if (argc != 4) {
    fprintf(stderr, "usage: noob-wav-gain INPUT.wav OUTPUT.wav MULTIPLIER\n"); return 2;
  }
  char *end;
  errno = 0;
  double gain = strtod(argv[3], &end);
  if (errno || *end || !isfinite(gain) || gain <= 0 || gain > 100) return 2;
  FILE *input = fopen(argv[1], "rb");
  if (!input) { perror("input"); return 1; }
  unsigned char header[44];
  if (fread(header, 1, 44, input) != 44 || memcmp(header, "RIFF", 4) ||
      memcmp(header+8, "WAVEfmt ", 8) || u32(header+16) != 16 ||
      u16(header+20) != 1 || u16(header+34) != 16 ||
      memcmp(header+36, "data", 4) || u32(header+40) % 2) {
    fprintf(stderr, "expected canonical 16-bit PCM WAV\n"); fclose(input); return 1;
  }
  FILE *output = fopen(argv[2], "wbx");
  if (!output) { perror("output (must not exist)"); fclose(input); return 1; }
  int failed = fwrite(header, 1, 44, output) != 44;
  uint32_t remaining = u32(header+40);
  unsigned clipped = 0;
  while (remaining && !failed) {
    unsigned char sample[2];
    if (fread(sample, 1, 2, input) != 2) { failed = 1; break; }
    double amplified = (int16_t)u16(sample) * gain;
    if (amplified > 32767) { amplified = 32767; ++clipped; }
    if (amplified < -32768) { amplified = -32768; ++clipped; }
    uint16_t result = (uint16_t)(int16_t)amplified;
    sample[0] = result & 255; sample[1] = result >> 8;
    if (fwrite(sample, 1, 2, output) != 2) failed = 1;
    remaining -= 2;
  }
  if (ferror(input)) failed = 1;
  fclose(input);
  if (fclose(output)) failed = 1;
  if (failed) { unlink(argv[2]); fprintf(stderr, "short WAV read/write\n"); return 1; }
  printf("gain=%.2f clipped_samples=%u\n", gain, clipped);
  return 0;
}
