#include <errno.h>
#include <fcntl.h>
#include <linux/i2c-dev.h>
#include <linux/i2c.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

static uint64_t start_us;

static uint64_t now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000u + (uint64_t)ts.tv_nsec / 1000u;
}

static int address_probe(int fd) {
    union i2c_smbus_data data;
    struct i2c_smbus_ioctl_data request = {
        .read_write = I2C_SMBUS_WRITE, .command = 0,
        .size = I2C_SMBUS_QUICK, .data = &data};
    return ioctl(fd, I2C_SMBUS, &request);
}

static int send_once(int fd, uint8_t control, uint8_t value) {
    const uint8_t bytes[] = {control, value};
    return write(fd, bytes, sizeof(bytes)) == (ssize_t)sizeof(bytes) ? 0 : -1;
}

static int stage(int fd, const char *name, uint8_t control, uint8_t value) {
    for (int attempt = 1; attempt <= 100; ++attempt) {
        if (attempt > 1) usleep(10000);
        errno = 0;
        int sent = send_once(fd, control, value);
        int send_errno = errno;
        if (sent == 0) {
            printf("%9llu us %-8s ACK try=%d\n",
                   (unsigned long long)(now_us() - start_us), name, attempt);
            fflush(stdout);
            return 0;
        }
        if (attempt == 1 || attempt % 10 == 0) {
            printf("%9llu us %-8s NACK try=%d errno=%d\n",
                   (unsigned long long)(now_us() - start_us), name, attempt,
                   send_errno);
            fflush(stdout);
        }
    }
    return -1;
}

int main(void) {
    int fd = open("/dev/i2c-1", O_RDWR);
    if (fd < 0 || ioctl(fd, I2C_SLAVE, 0x3c) < 0) {
        fprintf(stderr, "open/select: %s\n", strerror(errno));
        return 1;
    }
    start_us = now_us();
    int failures = 0;
    failures += stage(fd, "ON",   0x00, 0xaf) != 0;
    usleep(150000);
    failures += stage(fd, "RAM",  0x00, 0xa4) != 0;
    failures += stage(fd, "NORM", 0x00, 0xa6) != 0;
    failures += stage(fd, "PAGE0",0x00, 0xb0) != 0;
    failures += stage(fd, "COL_LO",0x00, 0x00) != 0;
    failures += stage(fd, "COL_HI",0x00, 0x10) != 0;
    failures += stage(fd, "PIXEL",0x40, 0x01) != 0;
    printf("complete: failed_stages=%d (target: page 0, column 0, bit 0)\n", failures);
    close(fd);
    return failures ? 1 : 0;
}
