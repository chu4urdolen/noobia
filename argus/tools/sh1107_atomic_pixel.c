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

int main(void) {
    int fd = open("/dev/i2c-1", O_RDWR);
    if (fd < 0 || ioctl(fd, I2C_SLAVE, 0x3c) < 0) return 1;

    // Co=1 command pairs keep the compound command stream alive; Co=0,D/C=1
    // marks the final byte as display RAM data. Every attempt is self-contained.
    const uint8_t message[] = {
        0x80, 0xb0,  // page 0
        0x80, 0x00,  // column low nibble 0
        0x80, 0x10,  // column high nibble 0
        0x40, 0x01   // one pixel: bit 0 at page 0, column 0
    };
    unsigned ack = 0;
    uint64_t start = now_us();
    for (unsigned attempt = 1; attempt <= 100; ++attempt) {
        errno = 0;
        ssize_t result = write(fd, message, sizeof(message));
        if (result == (ssize_t)sizeof(message)) ++ack;
        if (attempt == 1 || attempt % 10 == 0)
            printf("%9llu us attempt=%u complete_ACK=%u result=%zd errno=%d\n",
                   (unsigned long long)(now_us() - start), attempt, ack,
                   result, result < 0 ? errno : 0);
        usleep(20000);
    }
    printf("final: complete_ACK=%u/100 target=page0,column0,bit0\n", ack);
    close(fd);
    return 0;
}
