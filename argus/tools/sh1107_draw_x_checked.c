#include <errno.h>
#include <fcntl.h>
#include <linux/i2c-dev.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

/*
 * SH1107 128x128 test pattern for the GME128128-01-IIC.
 *
 * Unlike the early diagnostic, this driver checks every write.  Pixel data
 * is sent as one page transaction (control byte + 128 data bytes), rather
 * than 128 separate transactions.  That keeps the I2C bus quiet and makes a
 * failed page observable and retryable.
 */

static int write_retry(int fd, const uint8_t *buf, size_t len, const char *what)
{
    for (int attempt = 1; attempt <= 5; ++attempt) {
        ssize_t n = write(fd, buf, len);
        if (n == (ssize_t)len)
            return 0;
        fprintf(stderr, "%s attempt %d: wrote %zd/%zu (%s)\n",
                what, attempt, n, len, n < 0 ? strerror(errno) : "short write");
        usleep(5000);
    }
    return -1;
}

static int command(int fd, uint8_t value)
{
    uint8_t tx[2] = {0x00, value};
    return write_retry(fd, tx, sizeof tx, "command");
}

static int send_page(int fd, uint8_t page, const uint8_t pixels[128])
{
    uint8_t tx[129];
    tx[0] = 0x40;                 /* following bytes are display RAM data */
    memcpy(&tx[1], pixels, 128);
    if (command(fd, (uint8_t)(0xb0 | page)) < 0 ||
        command(fd, 0x00) < 0 || command(fd, 0x10) < 0)
        return -1;
    return write_retry(fd, tx, sizeof tx, "page data");
}

int main(void)
{
    int fd = open("/dev/i2c-1", O_RDWR);
    if (fd < 0) { perror("open /dev/i2c-1"); return 1; }
    if (ioctl(fd, I2C_SLAVE, 0x3c) < 0) { perror("I2C_SLAVE 0x3c"); return 1; }

    if (command(fd, 0xa4) < 0 || command(fd, 0xa6) < 0 || command(fd, 0xaf) < 0)
        return 1;
    usleep(100000);

    for (uint8_t page = 0; page < 16; ++page) {
        uint8_t pixels[128] = {0};
        for (uint8_t column = 0; column < 128; ++column) {
            if (column == 0 || column == 127) pixels[column] = 0xff;
            if ((column >> 3) == page)
                pixels[column] |= (uint8_t)(1u << (column & 7));
            uint8_t reverse = (uint8_t)(127 - column);
            if ((reverse >> 3) == page)
                pixels[column] |= (uint8_t)(1u << (reverse & 7));
            if (page == 0) pixels[column] |= 0x01;
            if (page == 15) pixels[column] |= 0x80;
        }
        if (send_page(fd, page, pixels) < 0) {
            fprintf(stderr, "page %u failed after retries\n", page);
            close(fd);
            return 2;
        }
        usleep(30000);            /* pause between complete page writes */
    }
    puts("checked page-burst X pattern sent");
    close(fd);
    return 0;
}
