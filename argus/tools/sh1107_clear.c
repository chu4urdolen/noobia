#include <fcntl.h>
#include <linux/i2c-dev.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <unistd.h>

static void send_pair(int fd, uint8_t control, uint8_t value) {
    const uint8_t bytes[] = {control, value};
    (void)write(fd, bytes, sizeof(bytes));
    usleep(1000);
}

int main(void) {
    int fd = open("/dev/i2c-1", O_RDWR);
    if (fd < 0 || ioctl(fd, I2C_SLAVE, 0x3c) < 0) return 1;

    send_pair(fd, 0x00, 0xa4);
    send_pair(fd, 0x00, 0xa6);
    send_pair(fd, 0x00, 0xaf);
    usleep(150000);

    for (uint8_t page = 0; page < 16; ++page) {
        send_pair(fd, 0x00, 0xb0 | page);
        send_pair(fd, 0x00, 0x00);
        send_pair(fd, 0x00, 0x10);
        for (uint8_t column = 0; column < 128; ++column)
            send_pair(fd, 0x40, 0x00);
    }

    puts("SH1107 RAM clear stream sent");
    close(fd);
    return 0;
}
