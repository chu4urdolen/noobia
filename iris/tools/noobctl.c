/* Native NRP/1 client for UART and USB serial Noob transports. */
#define _DEFAULT_SOURCE
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <termios.h>
#include <unistd.h>

int main(int argc, char **argv) {
  if (argc < 4) {
    fprintf(stderr, "usage: %s PORT REQUEST_ID COMMAND [ARGS...]\n", argv[0]);
    return 2;
  }
  int fd = open(argv[1], O_RDWR | O_NOCTTY);
  struct termios tty;
  if (fd < 0 || tcgetattr(fd, &tty) < 0) { perror("serial"); return 1; }
  cfmakeraw(&tty); cfsetispeed(&tty, B115200); cfsetospeed(&tty, B115200);
  tty.c_cflag |= CLOCAL | CREAD;
  if (tcsetattr(fd, TCSANOW, &tty) < 0) { perror("termios"); return 1; }
  int lines = TIOCM_DTR | TIOCM_RTS; ioctl(fd, TIOCMBIC, &lines);
  sleep(3); tcflush(fd, TCIFLUSH);  /* CH340 open may reset the Noob. */

  char frame[2300]; int used = snprintf(frame, sizeof(frame), "NRP/1 %s", argv[2]);
  for (int i=3; i<argc && used>0 && used<(int)sizeof(frame); ++i)
    used += snprintf(frame+used, sizeof(frame)-used, " %s", argv[i]);
  if (used<=0 || used+1>=(int)sizeof(frame)) return 2;
  frame[used++]='\n';
  if (write(fd, frame, used) != used) { perror("write"); return 1; }

  char prefix[128], line[4096]; size_t length=0;
  snprintf(prefix, sizeof(prefix), "NRP/1 %s ", argv[2]);
  // Allow for the preferred BLE transport to perform its bounded startup scan
  // before the cooperative runtime reaches this recovery transport.
  for (int attempt=0; attempt<75; ++attempt) {
    struct pollfd p={.fd=fd,.events=POLLIN}; if (poll(&p,1,200)<=0) continue;
    char bytes[256]; ssize_t count=read(fd,bytes,sizeof(bytes));
    if (count <= 0) { usleep(200000); continue; }
    for (ssize_t i=0;i<count;++i) {
      if (bytes[i]=='\n'||bytes[i]=='\r') {
        if (length) { line[length]=0; if (!strncmp(line,prefix,strlen(prefix))) { puts(line); close(fd); return 0; } length=0; }
      } else if (length+1<sizeof(line)) line[length++]=bytes[i];
    }
    usleep(200000);
  }
  fprintf(stderr,"no matching reply within 15 seconds\n"); close(fd); return 1;
}
