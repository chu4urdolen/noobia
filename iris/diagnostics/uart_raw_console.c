/* Raw CH340 UART console. Clears DTR/RTS and prints boot/panic output. */
#define _DEFAULT_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <termios.h>
#include <unistd.h>

static volatile sig_atomic_t stopped;
static void stop_console(int signal_number) {
  (void)signal_number;
  stopped = 1;
}

int main(int argc, char **argv) {
  if (argc != 2) {
    fprintf(stderr, "usage: %s /dev/ttyUSB0\n", argv[0]);
    return 2;
  }
  int fd = open(argv[1], O_RDWR | O_NOCTTY | O_NONBLOCK);
  if (fd < 0) {
    perror("serial open");
    return 1;
  }
  struct termios tty;
  if (tcgetattr(fd, &tty) < 0) {
    perror("tcgetattr");
    close(fd);
    return 1;
  }
  cfmakeraw(&tty);
  cfsetispeed(&tty, B115200);
  cfsetospeed(&tty, B115200);
  tty.c_cflag |= CLOCAL | CREAD;
  tty.c_cflag &= ~(HUPCL | CRTSCTS);
  if (tcsetattr(fd, TCSANOW, &tty) < 0) {
    perror("tcsetattr");
    close(fd);
    return 1;
  }
  int lines = TIOCM_DTR | TIOCM_RTS;
  if (ioctl(fd, TIOCMBIC, &lines) < 0 && errno != ENOTTY) {
    perror("clear DTR/RTS");
    close(fd);
    return 1;
  }

  signal(SIGINT, stop_console);
  signal(SIGTERM, stop_console);
  while (!stopped) {
    struct pollfd streams[2] = {
        {.fd = fd, .events = POLLIN},
        {.fd = STDIN_FILENO, .events = POLLIN}};
    int ready = poll(streams, 2, 1000);
    if (ready < 0 && errno == EINTR) continue;
    if (ready < 0) {
      perror("poll");
      break;
    }
    if (streams[0].revents & POLLIN) {
      char data[1024];
      ssize_t count = read(fd, data, sizeof(data));
      if (count > 0) {
        fwrite(data, 1, (size_t)count, stdout);
        fflush(stdout);
      }
    }
    if (streams[1].revents & POLLIN) {
      char data[1024];
      ssize_t count = read(STDIN_FILENO, data, sizeof(data));
      if (count <= 0) break;
      ssize_t written = write(fd, data, (size_t)count);
      if (written < 0 && errno != EAGAIN) {
        perror("write");
        break;
      }
    }
    if (streams[0].revents & (POLLERR | POLLHUP | POLLNVAL)) {
      fprintf(stderr, "serial disconnected\n");
      break;
    }
  }
  close(fd);
  return 0;
}
