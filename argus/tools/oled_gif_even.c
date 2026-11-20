/* Minimal GIF (first frame) -> SH1107 renderer.
 * Requires stb_image.h in tools/vendor and links no image library.
 */
#define STB_IMAGE_IMPLEMENTATION
#include "vendor/stb_image.h"
#include <fcntl.h>
#include <linux/i2c-dev.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <unistd.h>

static int tx(int fd, const uint8_t *p, size_t n) { for (size_t i = 0; i < n; ++i) if ((p[i] & 1u) && !(n == 2 && i == 1 && p[1] == 0xaf)) { fprintf(stderr, "refusing odd I2C byte 0x%02x at offset %zu\n", p[i], i); return -2; } return write(fd, p, n) == (ssize_t)n ? 0 : -1; }
static int cmd(int fd, uint8_t v) { uint8_t p[2] = {0x00, v}; return tx(fd, p, 2); }
static int cmd2(int fd, uint8_t a, uint8_t b) { uint8_t p[3] = {0x00, a, b}; return tx(fd, p, 3); }

static int init_display(int fd) {
  int error = 0;
  error |= cmd(fd, 0xae);
  error |= cmd2(fd, 0xdc, 0x00);
  error |= cmd(fd, 0x20);
  error |= cmd(fd, 0xa0);
  error |= cmd(fd, 0xc0);
  error |= cmd(fd, 0xda);
  error |= cmd(fd, 0x12);
  error |= cmd(fd, 0xa4);
  error |= cmd(fd, 0xa6);
  error |= cmd(fd, 0xaf); /* sole permitted odd byte */
  return error;
}

int main(int argc, char **argv) {
  if (argc != 2) { fprintf(stderr, "usage: %s image.gif\n", argv[0]); return 2; }
  int w, h, channels;
  unsigned char *src = stbi_load(argv[1], &w, &h, &channels, 1);
  if (!src) { fprintf(stderr, "decode failed: %s\n", stbi_failure_reason()); return 1; }
  int fd = open("/dev/i2c-1", O_RDWR);
  if (fd < 0 || ioctl(fd, I2C_SLAVE, 0x3c) < 0) { perror("i2c 0x3c"); return 1; }
  if (init_display(fd)) fprintf(stderr, "warning: init transaction reported an error; continuing only with checked page writes\n");
  uint8_t page[129];
  for (int pg = 0; pg < 16; pg += 2) {
    if (cmd(fd, (uint8_t)(0xb0 | pg)) || cmd(fd, 0x00) || cmd(fd, 0x10)) { fprintf(stderr, "page %d command NACK; stopping\n", pg); break; }
    page[0] = 0x40;
    for (int ram_x = 0; ram_x < 128; ++ram_x) {
      int x = (ram_x + 64) & 127; /* observed RAM column 0 is screen center */
      uint8_t bits = 0;
      for (int bit = 1; bit < 8; ++bit) { /* bit 0 is unreliable on this bus */
        int y = pg * 8 + bit - 1;       /* shift image down one row */
        int sx = (x * w) / 128, sy = (y * h) / 128;
        if (y < 128 && src[sy * w + sx] >= 128) bits |= (uint8_t)(1u << bit);
      }
      page[ram_x + 1] = bits & 0xfe;
    }
    if (tx(fd, page, sizeof page) < 0) { fprintf(stderr, "page %d even-data transaction failed; stopping\n", pg); break; }
  }
  cmd(fd, 0xaf); stbi_image_free(src); close(fd); return 0;
}
