/* One-shot NanoHat OLED smoke test for NanoPi NEO I2C0. */
#include <errno.h>
#include <fcntl.h>
#include <linux/i2c-dev.h>
#include <linux/i2c.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

enum { OLED_ADDRESS = 0x3c, WIDTH = 128, HEIGHT = 64, PAGES = HEIGHT / 8 };

static int write_bytes(int fd, const uint8_t *bytes, size_t length) {
  ssize_t written = write(fd, bytes, length);
  if (written == (ssize_t)length) return 0;
  if (written >= 0) errno = EIO;
  perror("I2C write");
  return -1;
}

static int command(int fd, const uint8_t *bytes, size_t length) {
  uint8_t packet[32];
  if (length + 1 > sizeof(packet)) {
    errno = EMSGSIZE;
    perror("OLED command");
    return -1;
  }
  packet[0] = 0x00;  /* SSD1306 command-control byte. */
  memcpy(packet + 1, bytes, length);
  return write_bytes(fd, packet, length + 1);
}

static void set_pixel(uint8_t image[PAGES][WIDTH], int x, int y) {
  if (x < 0 || x >= WIDTH || y < 0 || y >= HEIGHT) return;
  image[y / 8][x] |= (uint8_t)(1u << (y % 8));
}

static void draw_test_pattern(uint8_t image[PAGES][WIDTH]) {
  memset(image, 0, PAGES * WIDTH);
  /* Border, two diagonals, and a small center marker. */
  for (int x = 8; x < 120; ++x) {
    set_pixel(image, x, 7);
    set_pixel(image, x, 56);
  }
  for (int y = 7; y <= 56; ++y) {
    set_pixel(image, 8, y);
    set_pixel(image, 119, y);
    set_pixel(image, 31 + (y * 66 / 63), y);
    set_pixel(image, 96 - (y * 66 / 63), y);
  }
  for (int x = 60; x <= 67; ++x) {
    for (int y = 28; y <= 35; ++y) set_pixel(image, x, y);
  }
}

int main(int argc, char **argv) {
  const char *device = argc > 1 ? argv[1] : "/dev/i2c-0";
  int fd = open(device, O_RDWR | O_CLOEXEC);
  if (fd < 0) {
    perror(device);
    return 1;
  }
  if (ioctl(fd, I2C_SLAVE, OLED_ADDRESS) < 0) {
    perror("I2C_SLAVE");
    close(fd);
    return 1;
  }

  /* FriendlyELEC BakeBit/NanoHat OLED initialization sequence. */
  static const uint8_t init[] = {
      0xae, 0x00, 0x10, 0x40, 0xb0, 0x81, 0xcf, 0xa1, 0xa6, 0xa8, 0x3f,
      0xc8, 0xd3, 0x00, 0xd5, 0x80, 0xd9, 0xf1, 0xda, 0x12, 0xdb, 0x40,
      0x8d, 0x14, 0x20, 0x02, 0xaf};
  if (command(fd, init, sizeof(init)) < 0) {
    close(fd);
    return 1;
  }

  uint8_t image[PAGES][WIDTH];
  draw_test_pattern(image);
  for (int page = 0; page < PAGES; ++page) {
    const uint8_t position[] = {
        (uint8_t)(0xb0 + page), 0x00, 0x10};
    if (command(fd, position, sizeof(position)) < 0) {
      close(fd);
      return 1;
    }
    uint8_t data[WIDTH + 1];
    data[0] = 0x40;  /* One RAM data burst for this page. */
    memcpy(data + 1, image[page], WIDTH);
    if (write_bytes(fd, data, sizeof(data)) < 0) {
      close(fd);
      return 1;
    }
  }

  close(fd);
  puts("OLED pattern written: framed X with center marker");
  return 0;
}
