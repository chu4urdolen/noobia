#include <errno.h>
#include <fcntl.h>
#include <linux/i2c-dev.h>
#include <linux/i2c.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

static void probe(int fd, int address) {
    union i2c_smbus_data data;
    struct i2c_smbus_ioctl_data request = {
        .read_write = I2C_SMBUS_WRITE,
        .command = 0,
        .size = I2C_SMBUS_QUICK,
        .data = &data,
    };
    if (ioctl(fd, I2C_SLAVE, address) < 0) {
        printf("0x%02X select failed: %s\n", address, strerror(errno));
        return;
    }
    errno = 0;
    if (ioctl(fd, I2C_SMBUS, &request) == 0)
        printf("0x%02X address ACK\n", address);
    else
        printf("0x%02X address NACK: %s\n", address, strerror(errno));
}

int main(void) {
    int fd = open("/dev/i2c-1", O_RDWR);
    if (fd < 0) {
        fprintf(stderr, "open /dev/i2c-1: %s\n", strerror(errno));
        return 1;
    }
    probe(fd, 0x3c);
    probe(fd, 0x3d);
    close(fd);
    return 0;
}
