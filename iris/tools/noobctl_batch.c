/* Keep one UART connection open while sending several NRP/1 commands.
 * This avoids the ESP32 reset caused by reopening some USB/UART bridges. */
#define _DEFAULT_SOURCE
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <termios.h>
#include <unistd.h>

static int wait_reply(int fd, const char *id) {
  char prefix[64], line[4096];
  size_t length = 0;
  snprintf(prefix, sizeof(prefix), "NRP/1 %s ", id);
  for (int attempt = 0; attempt < 100; ++attempt) {
    struct pollfd descriptor = {.fd = fd, .events = POLLIN};
    if (poll(&descriptor, 1, 200) <= 0) continue;
    char bytes[256];
    const ssize_t count = read(fd, bytes, sizeof(bytes));
    for (ssize_t index = 0; index < count; ++index) {
      if (bytes[index] == 10 || bytes[index] == 13) {
        if (length) {
          line[length] = 0;
          if (!strncmp(line, prefix, strlen(prefix))) {
            puts(line);
            return 0;
          }
          length = 0;
        }
      } else if (length + 1 < sizeof(line)) {
        line[length++] = bytes[index];
      }
    }
  }
  fprintf(stderr, "no reply for %s\n", id);
  return 1;
}

int main(int argc, char **argv) {
  if (argc != 2) {
    fprintf(stderr, "usage: %s PORT < commands.txt\n", argv[0]);
    return 2;
  }
  const int fd = open(argv[1], O_RDWR | O_NOCTTY);
  struct termios tty;
  if (fd < 0 || tcgetattr(fd, &tty) < 0) { perror("serial"); return 1; }
  cfmakeraw(&tty);
  cfsetispeed(&tty, B115200);
  cfsetospeed(&tty, B115200);
  tty.c_cflag |= CLOCAL | CREAD;
  if (tcsetattr(fd, TCSANOW, &tty) < 0) { perror("termios"); return 1; }
  int lines = TIOCM_DTR | TIOCM_RTS;
  ioctl(fd, TIOCMBIC, &lines);
  sleep(3);
  tcflush(fd, TCIFLUSH);

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
        write(fd, frame, length) != length || wait_reply(fd, id)) {
      close(fd);
      return 1;
    }
  }
  close(fd);
  return 0;
}
