/* Bounded USB-CDC console for stock firmware; logs TX and RX, no boot reset. */
#define _DEFAULT_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t stopped;
static void stop(int sig) { (void)sig; stopped = 1; }
static long long now_ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (long long)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}
static int send_all(int fd, const char *data, size_t len) {
    long long deadline = now_ms() + 2000;
    while (len && !stopped) {
        ssize_t n = write(fd, data, len);
        if (n > 0) { data += n; len -= (size_t)n; continue; }
        if (n < 0 && errno != EAGAIN && errno != EINTR) return -1;
        if (now_ms() >= deadline) { errno = ETIMEDOUT; return -1; }
        struct pollfd out = {fd, POLLOUT, 0};
        if (poll(&out, 1, 100) < 0 && errno != EINTR) return -1;
    }
    return len ? -1 : 0;
}
int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "usage: %s /dev/ttyACM0 NEW_LOG_FILE\n", argv[0]);
        return 2;
    }
    int logfd = open(argv[2], O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (logfd < 0) { perror("new log"); return 1; }
    FILE *log = fdopen(logfd, "w");
    if (!log) { perror("fdopen"); close(logfd); return 1; }
    setvbuf(log, NULL, _IONBF, 0);
    int fd = open(argv[1], O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (fd < 0) { perror("serial open"); fclose(log); return 1; }
    struct termios tty;
    if (tcgetattr(fd, &tty) < 0) goto fail;
    cfmakeraw(&tty);
    cfsetispeed(&tty, B115200);
    cfsetospeed(&tty, B115200);
    tty.c_cflag |= CLOCAL | CREAD;
    tty.c_cflag &= ~(HUPCL | CRTSCTS);
    tty.c_cc[VMIN] = 0;
    tty.c_cc[VTIME] = 0;
    if (tcsetattr(fd, TCSANOW, &tty) < 0) goto fail;
    if (ioctl(fd, TIOCEXCL) < 0) goto fail;
    /* CDC uses DTR for connection readiness. Never use this on a UART bridge. */
    int dtr = TIOCM_DTR;
    if (ioctl(fd, TIOCMBIS, &dtr) < 0 && errno != ENOTTY) goto fail;
    signal(SIGINT, stop);
    signal(SIGTERM, stop);
    const long long started = now_ms(), deadline = started + 900000;
    fprintf(stderr, "CDC console open; 15-minute limit. Ctrl-D/Ctrl-C exits.\n");
    while (!stopped && now_ms() < deadline) {
        struct pollfd in[2] = {{fd, POLLIN, 0}, {STDIN_FILENO, POLLIN, 0}};
        int ready = poll(in, 2, 1000);
        if (ready < 0) { if (errno == EINTR) continue; goto fail; }
        if (in[0].revents & POLLIN) {
            char buf[4096];
            ssize_t n = read(fd, buf, sizeof(buf));
            if (n > 0) {
                fwrite(buf, 1, (size_t)n, stdout); fflush(stdout);
                fprintf(log, "\n[RX +%lldms] ", now_ms() - started);
                fwrite(buf, 1, (size_t)n, log);
            } else if (n < 0 && errno != EAGAIN && errno != EINTR) goto fail;
        }
        if (in[0].revents & (POLLERR | POLLHUP | POLLNVAL)) {
            fprintf(stderr, "CDC disconnected\n"); close(fd); fclose(log); return 1;
        }
        if (in[1].revents & POLLIN) {
            char buf[1024];
            ssize_t n = read(STDIN_FILENO, buf, sizeof(buf));
            if (n <= 0) break;
            for (ssize_t i = 0; i < n; ++i) if (buf[i] == '\n') buf[i] = '\r';
            fprintf(log, "\n[TX +%lldms] ", now_ms() - started);
            fwrite(buf, 1, (size_t)n, log);
            if (send_all(fd, buf, (size_t)n)) goto fail;
        }
        if (in[1].revents & (POLLERR | POLLHUP | POLLNVAL)) break;
    }
    fprintf(log, "\n[closed]\n");
    close(fd); fclose(log); return 0;
fail:
    perror("CDC console"); close(fd); fclose(log); return 1;
}
