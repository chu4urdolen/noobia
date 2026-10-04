#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void put16(FILE *f, unsigned value) {
  fputc(value & 255, f); fputc((value >> 8) & 255, f);
}
static void put32(FILE *f, uint32_t value) {
  put16(f, value & 65535); put16(f, value >> 16);
}

/* Generate a bounded stereo WAV; this program does not play sound itself. */
int main(int argc, char **argv) {
  if (argc != 5 && argc != 6) {
    fprintf(stderr, "usage: audio-tone OUT.wav FREQUENCY_HZ SECONDS PEAK_PERCENT [16|32]\n"); return 2;
  }
  char *end;
  double frequency = strtod(argv[2], &end);
  if (*end || !isfinite(frequency) || frequency < 100 || frequency > 4000) return 2;
  double duration = strtod(argv[3], &end);
  if (*end || !isfinite(duration) || duration <= 0 || duration > 10) return 2;
  double peak = strtod(argv[4], &end);
  if (*end || !isfinite(peak) || peak <= 0 || peak > 50) return 2;
  unsigned bits = argc == 6 ? (unsigned)strtoul(argv[5], &end, 10) : 16;
  if ((argc == 6 && *end) || (bits != 16 && bits != 32)) return 2;
  unsigned frame_bytes = 2 * bits / 8;
  uint32_t frames = (uint32_t)(48000 * duration), data_bytes = frames * frame_bytes;
  FILE *file = fopen(argv[1], "wbx");
  if (!file) { perror("output (must not exist)"); return 1; }
  fwrite("RIFF", 1, 4, file); put32(file, 36 + data_bytes);
  fwrite("WAVEfmt ", 1, 8, file); put32(file, 16);
  put16(file, 1); put16(file, 2); put32(file, 48000); put32(file, 48000 * frame_bytes);
  put16(file, frame_bytes); put16(file, bits); fwrite("data", 1, 4, file); put32(file, data_bytes);
  for (uint32_t i = 0; i < frames; ++i) {
    double fade = fmin(1.0, fmin((double)i / 480, (double)(frames-i-1) / 480));
    int16_t sample = (int16_t)(32767 * peak / 100 * fade *
        sin(2 * 3.141592653589793 * frequency * i / 48000));
    if (bits == 16) {
      put16(file, (uint16_t)sample); put16(file, (uint16_t)sample);
    } else {
      uint32_t wide = (uint32_t)((int32_t)sample * 65536);
      put32(file, wide); put32(file, wide);
    }
  }
  int failed = ferror(file);
  if (fclose(file)) failed = 1;
  return failed ? 1 : 0;
}
