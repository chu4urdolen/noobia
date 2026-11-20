#include <errno.h>
#include <fcntl.h>
#include <linux/i2c-dev.h>
#include <linux/i2c.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

static int smbus(int fd, char rw, uint8_t command, int size,
                 union i2c_smbus_data *data) {
    struct i2c_smbus_ioctl_data request = {
        .read_write = rw, .command = command, .size = size, .data = data};
    return ioctl(fd, I2C_SMBUS, &request);
}

static void command(int fd, uint8_t value, unsigned *ack) {
    union i2c_smbus_data data;
    data.byte = value;
    if (smbus(fd, I2C_SMBUS_WRITE, 0x00, I2C_SMBUS_BYTE_DATA, &data) == 0)
        ++*ack;
    usleep(100000);
}

static void block32(int fd, uint8_t phase, unsigned *ack) {
    union i2c_smbus_data data;
    data.block[0] = 32;
    for (int index = 0; index < 32; ++index)
        data.block[index + 1] = ((index + phase) & 1) ? 0xaa : 0x55;
    if (smbus(fd, I2C_SMBUS_WRITE, 0x40,
              I2C_SMBUS_I2C_BLOCK_DATA, &data) == 0)
        ++*ack;
    usleep(100000);
}

int main(void) {
    static const uint8_t init[] = {
        0xae, 0xd5, 0x50, 0x20, 0x81, 0x80, 0xa0, 0xa4, 0xa6,
        0xad, 0x80, 0xc0, 0xd9, 0x1f, 0xdb, 0x27, 0xaf,
        0xb0, 0x00, 0x10};
    int fd = open("/dev/i2c-1", O_RDWR);
    if (fd < 0 || ioctl(fd, I2C_SLAVE, 0x3c) < 0) {
        fprintf(stderr, "open/select: %s\n", strerror(errno));
        return 1;
    }
    unsigned command_ack = 0, block_ack = 0;
    for (size_t index = 0; index < sizeof(init); ++index)
        command(fd, init[index], &command_ack);
    for (uint8_t block = 0; block < 4; ++block)
        block32(fd, block, &block_ack);
    printf("Seeed sequence: command_ACK=%u/%zu page0_block_ACK=%u/4\n",
           command_ack, sizeof(init), block_ack);
    close(fd);
    return 0;
}
