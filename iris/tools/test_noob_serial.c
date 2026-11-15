/* PTY regression tests; never opens a physical serial port. */
#define _DEFAULT_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <pty.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

static int64_t now_ms(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (int64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}

static void send_bytes(int fd, const char *bytes) {
  size_t length = strlen(bytes);
  assert(write(fd, bytes, length) == (ssize_t)length);
}

static void run_case(const char *client, int batch, int no_reply) {
  int master, slave, in[2], out[2];
  char device[128];
  assert(openpty(&master, &slave, device, NULL, NULL) == 0);
  struct termios tty;
  assert(tcgetattr(slave, &tty) == 0);
  tty.c_cflag |= HUPCL | CRTSCTS;
  assert(tcsetattr(slave, TCSANOW, &tty) == 0);
  assert(pipe(in) == 0 && pipe(out) == 0);
  pid_t child = fork();
  assert(child >= 0);
  if (!child) {
    close(master); close(slave); close(in[1]); close(out[0]);
    assert(dup2(in[0], STDIN_FILENO) >= 0);
    assert(dup2(out[1], STDOUT_FILENO) >= 0);
    close(in[0]); close(out[1]);
    setenv("NOOB_SERIAL_SETTLE_MS", "0", 1);
    setenv("NOOB_SERIAL_TIMEOUT_MS", "450", 1);
    setenv("NOOB_SERIAL_EVENTS", "1", 1);
    if (batch) execl(client, client, device, NULL);
    else execl(client, client, device, "test", "PING", NULL);
    _exit(127);
  }
  close(in[0]); close(out[1]);
  if (batch) send_bytes(in[1], "PING\nCALL SD_INFO\nPING\n");
  close(in[1]);
  assert(fcntl(master, F_SETFL, O_NONBLOCK) == 0);
  char request[2400] = {0}, response[256], captured[4096] = {0};
  size_t used = 0;
  int requests = 0, replies = 0, status = 0, finished = 0;
  int phase = 0;
  int64_t start = now_ms(), received = 0;
  while (now_ms() - start < 3000) {
    char buf[256];
    ssize_t count = read(master, buf, sizeof(buf));
    for (ssize_t i = 0; i < count; ++i) {
      assert(used + 1 < sizeof(request));
      if (buf[i] == '\n') {
        request[used] = 0;
        char id[32];
        assert(sscanf(request, "NRP/1 %31s", id) == 1);
        assert(strstr(request, requests == 1 && batch ? "CALL SD_INFO" : "PING"));
        snprintf(response, sizeof(response), "NRP/1 %s OK PONG\n", id);
        received = now_ms(); used = 0; phase = 1; ++requests;
        assert(tcgetattr(slave, &tty) == 0);
        assert(!(tty.c_cflag & (HUPCL | CRTSCTS)));
      } else request[used++] = buf[i];
    }
    if (phase == 1) {
      if (!no_reply && now_ms() - received >= 220) {
        send_bytes(master, "NRP/1 unrelated OK ignored\n");
        assert(write(master, response, 5) == 5);
        phase = 2;
      } else {
        send_bytes(master, "background log\n");
      }
    } else if (phase == 2) {
      char combined[512];
      snprintf(combined, sizeof(combined), "%sNRP/1 0 EVENT RSSI scan=1 rssi=-60\n", response + 5);
      send_bytes(master, combined);
      phase = 0; ++replies;
    }
    if (waitpid(child, &status, WNOHANG) == child) { finished = 1; break; }
    usleep(1000);
  }
  if (!finished) { kill(child, SIGKILL); waitpid(child, &status, 0); }
  assert(finished && WIFEXITED(status));
  assert(WEXITSTATUS(status) == (no_reply ? 1 : 0));
  if (no_reply) assert(now_ms() - start >= 430 && now_ms() - start < 1000);
  assert(requests == (batch ? 3 : 1));
  assert(replies == (no_reply ? 0 : requests));
  ssize_t count = read(out[0], captured, sizeof(captured) - 1);
  assert(count >= 0);
  if (!no_reply) assert(strstr(captured, "OK PONG"));
  if (batch) assert(strstr(captured, "EVENT RSSI scan=1 rssi=-60"));
  close(out[0]); close(master); close(slave);
  printf("PASS %s: %s; HUPCL/CRTSCTS cleared\n", client,
         no_reply ? "deadline survives continuous logs" :
         batch ? "three requests, delayed fragmented replies under logs" :
                 "delayed fragmented reply under logs");
}

int main(int argc, char **argv) {
  assert(argc == 3);
  run_case(argv[1], 0, 0);
  run_case(argv[1], 0, 1);
  run_case(argv[2], 1, 0);
  return 0;
}
