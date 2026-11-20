#include <errno.h>
#include <fcntl.h>
#include <linux/i2c-dev.h>
#include <linux/i2c.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

static int command(int fd, unsigned char value) {
    unsigned char bytes[] = {0x00, value};
    struct i2c_msg message = {
        .addr = 0x3c,
        .flags = I2C_M_IGNORE_NAK,
        .len = sizeof(bytes),
        .buf = bytes,
    };
    struct i2c_rdwr_ioctl_data transaction = {
        .msgs = &message,
        .nmsgs = 1,
    };
    if (ioctl(fd, I2C_RDWR, &transaction) == 1) return 0;
    fprintf(stderr, "I2C write: %s\n", strerror(errno));
    return -1;
}

int main(void) {
    int fd = open("/dev/i2c-1", O_RDWR);
    if (fd < 0) {
        fprintf(stderr, "open /dev/i2c-1: %s\n", strerror(errno));
        return 1;
    }
    if (ioctl(fd, I2C_SLAVE, 0x3c) < 0) {
        fprintf(stderr, "select 0x3c: %s\n", strerror(errno));
        close(fd);
        return 1;
    }
    int acknowledged = 0;
    for (int attempt = 1; attempt <= 20; ++attempt) {
        if (command(fd, 0xaf) == 0) {
            ++acknowledged;
            printf("attempt %d: ACK\n", attempt);
            break;
        }
        printf("attempt %d: NACK\n", attempt);
        usleep(250000);
    }
    if (!acknowledged) {
        fprintf(stderr, "SH1107 at 0x3c acknowledged 0/20 attempts\n");
        close(fd);
        return 1;
    }
    usleep(150000); /* Datasheet requires recovery time after display-on. */
    if (command(fd, 0xa5)) {
        fprintf(stderr, "SH1107 at 0x3c did not accept display-on/all-on\n");
        close(fd);
        return 1;
    }
    puts("SH1107 0x3c acknowledged; all pixels forced on for 10 seconds");
    fflush(stdout);
    sleep(10);
    if (command(fd, 0xa4)) {
        fprintf(stderr, "warning: failed to restore RAM display mode\n");
        close(fd);
        return 1;
    }
    puts("restored normal RAM display mode");
    close(fd);
    return 0;
}
