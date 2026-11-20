#include <errno.h>
#include <fcntl.h>
#include <linux/i2c-dev.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

static uint64_t now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000u + (uint64_t)ts.tv_nsec / 1000u;
}

static void send_logged(int fd, unsigned number, const uint8_t *data,
                        size_t length, uint64_t start) {
    errno = 0;
    ssize_t result = write(fd, data, length);
    printf("%9llu us write=%u bytes=%zu result=%zd status=%s errno=%d\n",
           (unsigned long long)(now_us() - start), number, length, result,
           result == (ssize_t)length ? "ACK" : "NACK",
           result < 0 ? errno : 0);
    fflush(stdout);
}

int main(void) {
    int fd = open("/dev/i2c-1", O_RDWR);
    if (fd < 0 || ioctl(fd, I2C_SLAVE, 0x3c) < 0) {
        fprintf(stderr, "open/select: %s\n", strerror(errno));
        return 1;
    }
    const uint8_t display_on[] = {0x00, 0xaf};
    const uint8_t pixel[] = {
        0x80, 0xb0, // page 0
        0x80, 0x00, // column low 0
        0x80, 0x10, // column high 0
        0x40, 0x01  // page 0, column 0, bit 0
    };
    uint64_t start = now_us();
    send_logged(fd, 1, display_on, sizeof(display_on), start);
    usleep(150000);
    for (unsigned number = 2; number <= 10; ++number) {
        send_logged(fd, number, pixel, sizeof(pixel), start);
        if (number != 10) usleep(100000);
    }
    close(fd);
    return 0;
}
