/* Shared UART setup and wall-clock reply deadlines. */
#ifndef NOOB_SERIAL_H
#define NOOB_SERIAL_H
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

static int64_t serial_now_ms(void) {
  struct timespec now;
  clock_gettime(CLOCK_MONOTONIC, &now);
  return (int64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

static int serial_setting(const char *name, int fallback) {
  const char *value = getenv(name);
  char *end;
  if (!value || !*value) return fallback;
  errno = 0;
  long parsed = strtol(value, &end, 10);
  if (errno || *end || parsed < 0 || parsed > 120000) return fallback;
  return (int)parsed;
}

static int serial_open(const char *port) {
  int fd = open(port, O_RDWR | O_NOCTTY | O_NONBLOCK);
  struct termios tty;
  if (fd < 0) { perror("serial open"); return -1; }
  if (tcgetattr(fd, &tty) < 0) goto fail;
  cfmakeraw(&tty);
  cfsetispeed(&tty, B115200);
  cfsetospeed(&tty, B115200);
  tty.c_cflag |= CLOCAL | CREAD;
  /* Avoid resetting on close or inheriting hardware flow control. */
  tty.c_cflag &= ~(HUPCL | CRTSCTS);
  tty.c_cc[VMIN] = 0;
  tty.c_cc[VTIME] = 0;
  if (tcsetattr(fd, TCSANOW, &tty) < 0) goto fail;
  int lines = TIOCM_DTR | TIOCM_RTS;
  if (ioctl(fd, TIOCMBIC, &lines) < 0 && errno != ENOTTY) goto fail;
  /* Some bridges still reset on open. */
  int settle = serial_setting("NOOB_SERIAL_SETTLE_MS", 3000);
  struct timespec pause = {settle / 1000, (settle % 1000) * 1000000L};
  while (nanosleep(&pause, &pause) < 0 && errno == EINTR) {}
  if (tcflush(fd, TCIFLUSH) < 0) goto fail;
  return fd;
fail:
  perror("serial setup");
  close(fd);
  return -1;
}

static int serial_write(int fd, const char *frame, size_t length) {
  int64_t deadline = serial_now_ms() + 2000;
  while (length) {
    ssize_t count = write(fd, frame, length);
    if (count > 0) { frame += count; length -= (size_t)count; continue; }
    if (count < 0 && errno != EAGAIN && errno != EINTR) return -1;
    int remaining = (int)(deadline - serial_now_ms());
    if (remaining <= 0) { errno = ETIMEDOUT; return -1; }
    struct pollfd out = {.fd = fd, .events = POLLOUT};
    if (poll(&out, 1, remaining) < 0 && errno != EINTR) return -1;
  }
  return 0;
}

static unsigned serial_rssi_samples;
static int serial_wait_reply(int fd, const char *id) {
  char prefix[128], line[4096];
  size_t length = 0;
  int overflow = 0;
  int size = snprintf(prefix, sizeof(prefix), "NRP/1 %s ", id);
  if (size < 0 || size >= (int)sizeof(prefix)) return 1;
  int timeout = serial_setting("NOOB_SERIAL_TIMEOUT_MS", 15000);
  int64_t deadline = serial_now_ms() + timeout;
  while (serial_now_ms() < deadline) {
    int remaining = (int)(deadline - serial_now_ms());
    if (remaining <= 0) break;
    struct pollfd in = {.fd = fd, .events = POLLIN};
    int ready = poll(&in, 1, remaining);
    if (ready < 0 && errno == EINTR) continue;
    if (ready < 0) { perror("serial poll"); return 1; }
    if (!ready) break;
    /* Never consume bytes past this reply: the next frame may be an event. */
    char bytes[1];
    ssize_t count = read(fd, bytes, sizeof(bytes));
    if (count < 0 && (errno == EINTR || errno == EAGAIN)) continue;
    if (count <= 0) { fprintf(stderr, "serial disconnected\n"); return 1; }
    for (ssize_t i = 0; i < count; ++i) {
      if (bytes[i] == '\n' || bytes[i] == '\r') {
        if (length && !overflow) {
          line[length] = 0;
          if (!strncmp(line, prefix, (size_t)size)) {
            puts(line);
            return !strncmp(line + size, "ERR ", 4);
          }
          if (!strncmp(line, "NRP/1 0 EVENT ", 14)) {
            if (strstr(line, " EVENT RSSI ") && strstr(line, " rssi="))
              ++serial_rssi_samples;
            if (serial_setting("NOOB_SERIAL_EVENTS", 0)) puts(line);
          }
        }
        length = 0;
        overflow = 0;
      } else if (length + 1 < sizeof(line)) {
        line[length++] = bytes[i];
      } else {
        overflow = 1;
      }
    }
  }
  fprintf(stderr, "no reply for %s within %d ms after transmit\n", id, timeout);
  return 1;
}
#endif
