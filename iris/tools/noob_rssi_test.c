/* Bounded single-port VM and RSSI event test; no firmware changes. */
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
      request(fd, "load", "LOAD 2000700000211027200171000000") ||
      request(fd, "run", "RUN");
  int64_t deadline = serial_now_ms() + 16000;
  for (unsigned poll = 0; !failed && serial_now_ms() < deadline; ++poll) {
    char id[32];
    snprintf(id, sizeof(id), "poll%u", poll);
    failed |= request(fd, id, "PING");
    usleep(500000);
  }
  failed |= request(fd, "status", "STATUS");
  /* Always attempt cleanup, including on errors. */
  failed |= request(fd, "off", "CALL RSSI_OFF");
  failed |= request(fd, "stop", "STOP");
  failed |= request(fd, "alive", "PING");
  close(fd);
  printf("RSSI samples received: %u\n", serial_rssi_samples);
  return failed || !serial_rssi_samples;
}
