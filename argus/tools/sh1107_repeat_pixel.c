#include <errno.h>
#include <fcntl.h>
#include <linux/i2c-dev.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

static uint64_t now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000u + (uint64_t)ts.tv_nsec / 1000u;
}

static int pair(int fd, uint8_t control, uint8_t value) {
    const uint8_t bytes[] = {control, value};
    errno = 0;
    return write(fd, bytes, sizeof(bytes)) == (ssize_t)sizeof(bytes);
}

int main(void) {
    int fd = open("/dev/i2c-1", O_RDWR);
    if (fd < 0 || ioctl(fd, I2C_SLAVE, 0x3c) < 0) return 1;
    unsigned page_ack = 0, low_ack = 0, high_ack = 0, pixel_ack = 0;
    uint64_t start = now_us();
    for (unsigned cycle = 1; cycle <= 100; ++cycle) {
        // 0x80 is the per-command control byte used by the working reference.
        page_ack += pair(fd, 0x80, 0xb0);
        low_ack += pair(fd, 0x80, 0x00);
        high_ack += pair(fd, 0x80, 0x10);
        pixel_ack += pair(fd, 0x40, 0x01);
        if (cycle == 1 || cycle % 10 == 0)
            printf("%9llu us cycle=%u ACK page=%u low=%u high=%u pixel=%u\n",
                   (unsigned long long)(now_us() - start), cycle, page_ack,
                   low_ack, high_ack, pixel_ack);
        usleep(20000);
    }
    printf("final/100: page=%u low=%u high=%u pixel=%u\n",
           page_ack, low_ack, high_ack, pixel_ack);
    close(fd);
    return 0;
}
