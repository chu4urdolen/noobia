/* Native NRP/1 client for UART and USB serial Noob transports. */
#define _DEFAULT_SOURCE
#include "noob_serial.h"

int main(int argc, char **argv) {
  if (argc < 4) {
    fprintf(stderr, "usage: %s PORT REQUEST_ID COMMAND [ARGS...]\n", argv[0]);
    return 2;
  }
  int fd = serial_open(argv[1]);
  if (fd < 0) return 1;

  char frame[2300]; int used = snprintf(frame, sizeof(frame), "NRP/1 %s", argv[2]);
  for (int i=3; i<argc && used>0 && used<(int)sizeof(frame); ++i)
    used += snprintf(frame+used, sizeof(frame)-used, " %s", argv[i]);
  if (used<=0 || used+1>=(int)sizeof(frame)) { close(fd); return 2; }
  frame[used++]='\n';
  if (serial_write(fd, frame, (size_t)used)) { perror("write"); close(fd); return 1; }
  int result = serial_wait_reply(fd, argv[2]);
  close(fd);
  return result;
}
