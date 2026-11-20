#include <fcntl.h>
#include <linux/i2c-dev.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <unistd.h>

// GME128128-01-IIC accepts bytes but does not reliably ACK data. Transmit each
// byte once and deliberately ignore the Linux write status, matching the
// confirmed working low-level reference driver.
static void send_pair(int fd, uint8_t control, uint8_t value) {
    const uint8_t bytes[] = {control, value};
    (void)write(fd, bytes, sizeof(bytes));
    usleep(1000);
}

int main(void) {
    int fd = open("/dev/i2c-1", O_RDWR);
    if (fd < 0 || ioctl(fd, I2C_SLAVE, 0x3c) < 0) return 1;

    send_pair(fd, 0x00, 0xa4); // Display RAM, not forced-all mode.
    send_pair(fd, 0x00, 0xa6); // Normal, not inverted.
    send_pair(fd, 0x00, 0xaf); // Display on.
    usleep(150000);

    for (uint8_t page = 0; page < 16; ++page) {
        send_pair(fd, 0x00, (uint8_t)(0xb0 | page));
        send_pair(fd, 0x00, 0x00);
        send_pair(fd, 0x00, 0x10);
        for (uint8_t column = 0; column < 128; ++column) {
            uint8_t pixels = 0;
            if (column == 0 || column == 127) pixels = 0xff;
            if (page == 0) pixels |= 0x01;
            if (page == 15) pixels |= 0x80;
            if ((column >> 3) == page)
                pixels |= (uint8_t)(1u << (column & 7));
            uint8_t reverse = (uint8_t)(127 - column);
            if ((reverse >> 3) == page)
                pixels |= (uint8_t)(1u << (reverse & 7));
            send_pair(fd, 0x40, pixels);
        }
    }
    puts("sent one-pass 128x128 border-and-X pattern");
    close(fd);
    return 0;
}
