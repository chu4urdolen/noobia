#include <fcntl.h>
#include <linux/i2c-dev.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <unistd.h>

// Retry a complete control/value pair when the Pi I2C controller reports an
// aborted transfer. The OLED byte stream is otherwise identical to the
// original sh1107_draw_x diagnostic.
static unsigned send_pair_retry(int fd, uint8_t control, uint8_t value) {
    const uint8_t bytes[] = {control, value};
    for (unsigned attempt = 1; attempt <= 20; ++attempt) {
        if (write(fd, bytes, sizeof(bytes)) == (ssize_t)sizeof(bytes))
            return attempt;
        usleep(2000);
    }
    return 0;
}

int main(void) {
    int fd = open("/dev/i2c-1", O_RDWR);
    if (fd < 0 || ioctl(fd, I2C_SLAVE, 0x3c) < 0) return 1;

    unsigned failed = 0;
    send_pair_retry(fd, 0x00, 0xa4);
    send_pair_retry(fd, 0x00, 0xa6);
    send_pair_retry(fd, 0x00, 0xaf);
    usleep(150000);

    for (uint8_t page = 0; page < 16; ++page) {
        if (!send_pair_retry(fd, 0x00, 0xb0 | page)) ++failed;
        if (!send_pair_retry(fd, 0x00, 0x00)) ++failed;
        if (!send_pair_retry(fd, 0x00, 0x10)) ++failed;
        for (uint8_t column = 0; column < 128; ++column) {
            uint8_t pixels = 0;
            if (column == 0 || column == 127) pixels = 0xff;
            if (page == 0) pixels |= 0x01;
            if (page == 15) pixels |= 0x80;
            if ((column >> 3) == page) pixels |= 1u << (column & 7);
            uint8_t reverse = 127 - column;
            if ((reverse >> 3) == page)
                pixels |= 1u << (reverse & 7);
            if (!send_pair_retry(fd, 0x40, pixels)) ++failed;
        }
    }

    printf("retrying border/X complete; unrecovered_pairs=%u\n", failed);
    close(fd);
    return failed ? 1 : 0;
}
