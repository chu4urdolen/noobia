#include <errno.h>
#include <fcntl.h>
#include <linux/i2c-dev.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <unistd.h>

static int send_pair(int fd, uint8_t control, uint8_t value) {
    const uint8_t bytes[] = {control, value};
    return write(fd, bytes, sizeof(bytes)) == (ssize_t)sizeof(bytes);
}

static int command_retry(int fd, uint8_t command) {
    for (int attempt = 0; attempt < 100; ++attempt) {
        if (send_pair(fd, 0x80, command)) return attempt + 1;
        usleep(10000);
    }
    return 0;
}

int main(void) {
    int fd = open("/dev/i2c-1", O_RDWR);
    if (fd < 0 || ioctl(fd, I2C_SLAVE, 0x3c) < 0) return 1;

    int on_tries = command_retry(fd, 0xaf);
    usleep(150000);
    int ram_tries = command_retry(fd, 0xa4);
    int normal_tries = command_retry(fd, 0xa6);
    printf("startup: ON=%d RAM=%d NORMAL=%d attempts\n",
           on_tries, ram_tries, normal_tries);

    uint32_t random = 0x49524953u; // Reproducible "IRIS" seed.
    unsigned addressed = 0, data_acked = 0;
    for (unsigned point = 0; point < 100; ++point) {
        random = random * 1664525u + 1013904223u;
        uint8_t x = (uint8_t)(random >> 24);
        random = random * 1664525u + 1013904223u;
        uint8_t y = (uint8_t)(random >> 24);
        x &= 127;
        y &= 127;

        int page = command_retry(fd, (uint8_t)(0xb0 | (y >> 3)));
        int low = command_retry(fd, (uint8_t)(x & 0x0f));
        int high = command_retry(fd, (uint8_t)(0x10 | (x >> 4)));
        if (page && low && high) ++addressed;
        data_acked += send_pair(fd, 0x40, (uint8_t)(1u << (y & 7)));
        usleep(2000);
    }
    printf("points=100 addressed=%u data_ACK=%u\n", addressed, data_acked);
    close(fd);
    return 0;
}
