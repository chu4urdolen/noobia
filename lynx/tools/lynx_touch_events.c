/* Read-only, bounded Linux input-event probe for Lynx's Synaptics panel. */
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

static int64_t monotonic_ms(void)
{
	struct timespec ts;
	if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0)
		return -1;
	return (int64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

int main(int argc, char **argv)
{
	if (argc != 2) {
		fprintf(stderr, "usage: %s SECONDS(1..30)\n", argv[0]);
		return 2;
	}
	char *end;
	long seconds = strtol(argv[1], &end, 10);
	if (!*argv[1] || *end || seconds < 1 || seconds > 30)
		return 2;
	int fd = open("/dev/input/event0", O_RDONLY | O_NONBLOCK | O_CLOEXEC);
	if (fd < 0) {
		perror("open event0");
		return 1;
	}
	for (unsigned int code = ABS_MT_POSITION_X; code <= ABS_MT_POSITION_Y; code++) {
		struct input_absinfo axis;
		if (ioctl(fd, EVIOCGABS(code), &axis) == 0)
			printf("axis=%u min=%d max=%d\n", code, axis.minimum, axis.maximum);
	}
	fflush(stdout);
	int64_t deadline = monotonic_ms() + seconds * 1000;
	unsigned int count = 0;
	while (monotonic_ms() < deadline && count < 512) {
		int64_t left = deadline - monotonic_ms();
		if (left <= 0)
			break;
		struct pollfd pfd = { .fd = fd, .events = POLLIN };
		int ready = poll(&pfd, 1, left > 1000 ? 1000 : (int)left);
		if (ready < 0 && errno == EINTR)
			continue;
		if (ready < 0) {
			perror("poll event0");
			close(fd);
			return 1;
		}
		if (!ready)
			continue;
		if (pfd.revents & (POLLERR | POLLHUP | POLLNVAL)) {
			fprintf(stderr, "event0 poll error: %#x\n", pfd.revents);
			close(fd);
			return 1;
		}
		struct input_event event;
		ssize_t n = read(fd, &event, sizeof(event));
		if (n < 0 && (errno == EAGAIN || errno == EINTR))
			continue;
		if (n != sizeof(event)) {
			fprintf(stderr, "event0 short read: %zd\n", n);
			close(fd);
			return 1;
		}
		printf("%ld.%06ld type=%u code=%u value=%d\n",
		       (long)event.time.tv_sec, (long)event.time.tv_usec,
		       event.type, event.code, event.value);
		fflush(stdout);
		count++;
	}
	printf("events=%u\n", count);
	close(fd);
	return 0;
}
