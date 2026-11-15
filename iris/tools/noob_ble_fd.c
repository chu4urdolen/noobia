/*
 * Minimal native helper for the BlueZ bluetoothctl GATT test harness.
 *
 * bluetoothctl owns the server-side AcquireNotify SOCK_SEQPACKET descriptor
 * but exposes no command for writing dynamic characteristic values. This tool
 * duplicates that descriptor with pidfd_getfd and writes one NRP/1 frame.
 * It is a diagnostic bridge, not the long-term daemon architecture.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

int main(int argc, char **argv) {
  if (argc != 4) {
    fprintf(stderr, "usage: %s BLUETOOTHCTL_PID NOTIFY_FD NRP_FRAME\n", argv[0]);
    return 2;
  }
  const pid_t pid = (pid_t)strtol(argv[1], NULL, 10);
  const int target_fd = (int)strtol(argv[2], NULL, 10);
  const int pidfd = syscall(SYS_pidfd_open, pid, 0);
  if (pidfd < 0) {
    perror("pidfd_open");
    return 1;
  }
  const int fd = syscall(SYS_pidfd_getfd, pidfd, target_fd, 0);
  close(pidfd);
  if (fd < 0) {
    perror("pidfd_getfd");
    return 1;
  }
  const size_t length = strlen(argv[3]);
  const ssize_t written = write(fd, argv[3], length);
  close(fd);
  if (written < 0) {
    perror("write");
    return 1;
  }
  if ((size_t)written != length) {
    fprintf(stderr, "short write: %zd of %zu\n", written, length);
    return 1;
  }
  printf("sent %zu bytes\n", length);
  return 0;
}
