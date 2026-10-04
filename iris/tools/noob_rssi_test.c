/* Bounded RSSI thread test; leaves the current VM unchanged. */
#define _DEFAULT_SOURCE
#include "noob_serial.h"

static int request(int fd, const char *id, const char *command) {
  char frame[256];
  int length = snprintf(frame, sizeof(frame), "NRP/1 %s %s\n", id, command);
  return serial_write(fd, frame, (size_t)length) || serial_wait_reply(fd, id);
}

int main(int argc, char **argv) {
  if (argc != 2) { fprintf(stderr, "usage: %s PORT\n", argv[0]); return 2; }
  setenv("NOOB_SERIAL_EVENTS", "1", 1);
  setvbuf(stdout, NULL, _IOLBF, 0);
  int fd = serial_open(argv[1]);
  if (fd < 0) return 1;
  int failed = request(fd, "ping", "PING") ||
      request(fd, "start", "CALL RSSI_THREAD_START 10000 1000");
  int64_t deadline = serial_now_ms() + 16000;
  for (unsigned poll = 0; !failed && serial_now_ms() < deadline; ++poll) {
    char id[32];
    snprintf(id, sizeof(id), "poll%u", poll);
    failed |= request(fd, id, "CALL RSSI_THREAD_STATUS");
    usleep(500000);
  }
  failed |= request(fd, "status", "STATUS");
  /* Always attempt cleanup, including on errors. */
  failed |= request(fd, "off", "CALL RSSI_THREAD_STOP");
  failed |= request(fd, "alive", "PING");
  close(fd);
  return failed;
}
