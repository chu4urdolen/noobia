#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <linux/lirc.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

static int64_t now_ms(void) {
  struct timespec now;
  clock_gettime(CLOCK_MONOTONIC, &now);
  return (int64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

int main(int argc, char **argv) {
  if (argc != 3) {
    fprintf(stderr, "usage: ir-raw-probe /dev/lircN SECONDS(1..30)\n"); return 2;
  }
  char *end;
  long seconds = strtol(argv[2], &end, 10);
  if (*end || seconds < 1 || seconds > 30) return 2;
  int fd = open(argv[1], O_RDONLY | O_NONBLOCK);
  if (fd < 0) { perror("receiver"); return 1; }
  unsigned mode = LIRC_MODE_MODE2;
  if (ioctl(fd, LIRC_SET_REC_MODE, &mode)) { perror("raw mode"); close(fd); return 1; }
  int64_t start = now_ms(), deadline = start + seconds * 1000;
  unsigned pulses = 0, spaces = 0, timeouts = 0, count = 0;
  puts("READY raw IR receiver"); fflush(stdout);
  while (now_ms() < deadline) {
    struct pollfd ready = {.fd = fd, .events = POLLIN};
    int timeout = (int)(deadline - now_ms());
    int result = poll(&ready, 1, timeout > 0 ? timeout : 0);
    if (result < 0 && errno == EINTR) continue;
    if (result < 0 || (ready.revents & (POLLERR | POLLHUP | POLLNVAL))) {
      fprintf(stderr, "receiver poll failed\n"); close(fd); return 1;
    }
    if (!result) break;
    uint32_t samples[128];
    ssize_t bytes = read(fd, samples, sizeof(samples));
    if (bytes < 0 && errno == EAGAIN) continue;
    if (bytes <= 0 || bytes % sizeof(uint32_t)) { close(fd); return 1; }
    for (ssize_t i = 0; i < bytes / (ssize_t)sizeof(uint32_t); ++i) {
      unsigned type = LIRC_MODE2(samples[i]), value = LIRC_VALUE(samples[i]);
      pulses += type == LIRC_MODE2_PULSE;
      spaces += type == LIRC_MODE2_SPACE;
      timeouts += type == LIRC_MODE2_TIMEOUT;
      if (count++ < 32) printf("at_ms=%lld type=0x%x duration_us=%u\n",
                               (long long)(now_ms()-start), type, value);
    }
  }
  close(fd);
  printf("samples=%u pulses=%u spaces=%u timeouts=%u\n", count, pulses, spaces, timeouts);
  return 0;
}
