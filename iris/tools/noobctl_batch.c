/* Keep one UART connection open while sending several NRP/1 commands.
 * This avoids the ESP32 reset caused by reopening some USB/UART bridges. */
#define _DEFAULT_SOURCE
#include "noob_serial.h"

int main(int argc, char **argv) {
  if (argc != 2) {
    fprintf(stderr, "usage: %s PORT < commands.txt\n", argv[0]);
    return 2;
  }
  const int fd = serial_open(argv[1]);
  if (fd < 0) return 1;

  char command[2300];
  unsigned sequence = 0;
  while (fgets(command, sizeof(command), stdin)) {
    command[strcspn(command, "\r\n")] = 0;
    if (!command[0] || command[0] == '#') continue;
    char id[32], frame[2400];
    snprintf(id, sizeof(id), "batch%u", ++sequence);
    const int length = snprintf(frame, sizeof(frame), "NRP/1 %s %s\n", id,
                                command);
    if (length < 0 || length >= (int)sizeof(frame) ||
        serial_write(fd, frame, (size_t)length) || serial_wait_reply(fd, id)) {
      close(fd);
      return 1;
    }
  }
  close(fd);
  return 0;
}
