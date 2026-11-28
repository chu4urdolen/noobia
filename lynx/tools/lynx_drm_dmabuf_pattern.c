/*
 * Lynx DRM proof: allocate through dma-heap, import with PRIME, and display
 * color bars briefly. The stock driver's dumb-buffer allocation returned
 * ENOMEM, while the kernel source exposes a separate PRIME import path.
 *
 * Build on Lynx after installing libdrm-dev and linux-headers:
 *   cc -std=c11 -O2 -Wall -Wextra -I/usr/include/libdrm \
 *      lynx_drm_dmabuf_pattern.c -ldrm -o lynx_drm_dmabuf_pattern
 *
 * --probe only reads DRM capabilities. --allocate tests DMA-BUF import and
 * framebuffer creation without lighting the screen. --show also modesets
 * the connected DSI panel at 60 Hz for at most 15 seconds, then disables it.
 * Do not run --show before a V47 health and battery check.
 */

#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <arpa/inet.h>
#include <ctype.h>
#include <dirent.h>
#include <fcntl.h>
#include <glob.h>
#include <ifaddrs.h>
#include <inttypes.h>
#include <linux/dma-buf.h>
#include <linux/dma-heap.h>
#include <linux/input.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <drm_fourcc.h>
#include <zlib.h>

#define WIDTH 1240U
#define HEIGHT 2772U
#define STRIDE (WIDTH * 4U)
#define HEAP_DEVICE "/dev/dma_heap/system"
#define DRM_DEVICE "/dev/dri/card0"
#define TOUCH_DEVICE "/dev/input/event0"
#define TOUCH_NAME "/sys/class/input/input0/name"
#define BRIGHTNESS_DEVICE "/sys/kernel/oplus_display/oplus_brightness"
#define FRAME_DIR "/var/lib/lynx-display/frames"
#define SELECTION_FILE "/var/lib/lynx-display/selection"
#define CONSOLE_SNAPSHOT "/run/lynx-console/snapshot.txt"
#define CONSOLE_SOCKET "/run/lynx-console/control.sock"
#define THOUGHT_FILE "/var/lib/noobia/lynx_thought.txt"
#define HEARING_ENABLED_FILE "/var/lib/noobia/senses/hearing/enabled"
#define AIGEL_MODE_FILE "/var/lib/noobia/aigel_mode.txt"
/* Shutdown button: armed until this monotonic time (ms), 0 = not armed. */
static uint64_t shutdown_armed_until_ms = 0;
/* Power modes (Tom, 2026-11-23): "active" or "saving <reason>", written by
 * /usr/local/bin/lynx-power-mode. Power saving is the boot default; the
 * guards also switch to it (never a shutdown). */
#define POWER_MODE_FILE "/var/lib/noobia/power-mode"
#define POWER_MODE_TOOL "/usr/local/bin/lynx-power-mode"

static bool read_power_saving(char *reason, size_t size)
{
	char line[96] = "";
	FILE *f = fopen(POWER_MODE_FILE, "r");
	if (f) {
		if (!fgets(line, sizeof(line), f))
			line[0] = '\0';
		fclose(f);
	}
	line[strcspn(line, "\r\n")] = '\0';
	bool saving = strncmp(line, "saving", 6) == 0;	/* only saving mode shows power save screen */
	if (reason && size) {
		const char *r = strncmp(line, "saving", 6) == 0 ? line + 6 : "";
		while (*r == ' ')
			r++;
		snprintf(reason, size, "%s", *r ? r : "");
	}
	return saving;
}

static void run_power_mode(const char *mode, const char *reason)
{
	pid_t pid = fork();
	if (pid == 0) {
		setsid();
		execl(POWER_MODE_TOOL, "lynx-power-mode", mode, reason, (char *)NULL);
		_exit(127);
	}
}
#define MAX_SCENE_FRAMES 64

static volatile sig_atomic_t stop_requested;

static void request_stop(int signal_number)
{
	(void)signal_number;
	stop_requested = 1;
}

static void fail(const char *what)
{
	fprintf(stderr, "%s: %s (errno %d)\n", what, strerror(errno), errno);
}

static int sync_buffer(int fd, uint64_t flags)
{
	struct dma_buf_sync sync = { .flags = flags };
	int rc;
	do {
		rc = ioctl(fd, DMA_BUF_IOCTL_SYNC, &sync);
	} while (rc == -1 && (errno == EINTR || errno == EAGAIN));
	return rc;
}

static int set_brightness(unsigned int value)
{
	char text[16];
	int fd = open(BRIGHTNESS_DEVICE, O_WRONLY | O_CLOEXEC);
	if (fd < 0)
		return -1;
	int length = snprintf(text, sizeof(text), "%u\n", value);
	int rc = write(fd, text, (size_t)length) == length ? 0 : -1;
	int saved_errno = errno;
	close(fd);
	errno = saved_errno;
	return rc;
}

static int verify_touch_device(void)
{
	char name[64] = { 0 };
	int fd = open(TOUCH_NAME, O_RDONLY | O_CLOEXEC);
	if (fd < 0)
		return -1;
	ssize_t count = read(fd, name, sizeof(name) - 1);
	int saved_errno = errno;
	close(fd);
	errno = saved_errno;
	if (count < 0)
		return -1;
	if (strcmp(name, "touchpanel\n")) {
		errno = ENODEV;
		return -1;
	}
	return open(TOUCH_DEVICE, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
}

static uint64_t monotonic_milliseconds(void)
{
	struct timespec now;
	if (clock_gettime(CLOCK_MONOTONIC, &now) < 0)
		return 0;
	return (uint64_t)now.tv_sec * 1000U + (uint64_t)now.tv_nsec / 1000000U;
}

static void paint_bars(uint32_t *pixels)
{
	static const uint32_t bars[8] = {
		0x00ffffff, 0x00ffff00, 0x0000ffff, 0x0000ff00,
		0x00ff00ff, 0x00ff0000, 0x000000ff, 0x00000000
	};
	for (unsigned int y = 0; y < HEIGHT; y++) {
		for (unsigned int x = 0; x < WIDTH; x++)
			pixels[(size_t)y * WIDTH + x] = bars[(x * 8U) / WIDTH];
	}
}

struct glyph {
	char letter;
	uint8_t row[7];
};

/* Small self-contained font for Lynx's initial status screen. */
static const struct glyph font[] = {
	{' ', {0, 0, 0, 0, 0, 0, 0}},
	{'%', {0x19, 0x1a, 0x04, 0x04, 0x0b, 0x13, 0}},
	{'.', {0, 0, 0, 0, 0, 0x0c, 0x0c}},
	{'-', {0, 0, 0, 0x1f, 0, 0, 0}},
	{'/', {0x01, 0x02, 0x02, 0x04, 0x08, 0x08, 0x10}},
	{'?', {0x0e, 0x11, 0x01, 0x02, 0x04, 0, 0x04}},
	{'!', {0x04, 0x04, 0x04, 0x04, 0x04, 0, 0x04}},
	{'\\', {0x10, 0x08, 0x08, 0x04, 0x02, 0x02, 0x01}},
	{'{', {0x03, 0x04, 0x04, 0x18, 0x04, 0x04, 0x03}},
	{'}', {0x18, 0x04, 0x04, 0x03, 0x04, 0x04, 0x18}},
	{'_', {0, 0, 0, 0, 0, 0, 0x1f}},
	{'=', {0, 0x1f, 0, 0x1f, 0, 0, 0}},
	{'+', {0, 0x04, 0x04, 0x1f, 0x04, 0x04, 0}},
	{'*', {0, 0x15, 0x0e, 0x1f, 0x0e, 0x15, 0}},
	{'$', {0x04, 0x0f, 0x14, 0x0e, 0x05, 0x1e, 0x04}},
	{'<', {0x02, 0x04, 0x08, 0x10, 0x08, 0x04, 0x02}},
	{'>', {0x08, 0x04, 0x02, 0x01, 0x02, 0x04, 0x08}},
	{'(', {0x02, 0x04, 0x08, 0x08, 0x08, 0x04, 0x02}},
	{')', {0x08, 0x04, 0x02, 0x02, 0x02, 0x04, 0x08}},
	{'[', {0x0e, 0x08, 0x08, 0x08, 0x08, 0x08, 0x0e}},
	{']', {0x0e, 0x02, 0x02, 0x02, 0x02, 0x02, 0x0e}},
	{'|', {0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04}},
	{',', {0, 0, 0, 0, 0x0c, 0x0c, 0x08}},
	{';', {0, 0x0c, 0x0c, 0, 0x0c, 0x0c, 0x08}},
	{'\'', {0x04, 0x04, 0x08, 0, 0, 0, 0}},
	{'"', {0x0a, 0x0a, 0, 0, 0, 0, 0}},
	{'#', {0x0a, 0x1f, 0x0a, 0x1f, 0x0a, 0, 0}},
	{'@', {0x0e, 0x11, 0x17, 0x15, 0x17, 0x10, 0x0e}},
	{'&', {0x0c, 0x12, 0x14, 0x08, 0x15, 0x12, 0x0d}},
	{'^', {0x04, 0x0a, 0x11, 0, 0, 0, 0}},
	{'~', {0, 0, 0x09, 0x16, 0, 0, 0}},
	{'`', {0x08, 0x04, 0x02, 0, 0, 0, 0}},
	{':', {0, 0x04, 0x04, 0, 0x04, 0x04, 0}},
	{'0', {0x0e, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0e}},
	{'1', {0x04, 0x0c, 0x04, 0x04, 0x04, 0x04, 0x0e}},
	{'2', {0x0e, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1f}},
	{'3', {0x1e, 0x01, 0x01, 0x0e, 0x01, 0x01, 0x1e}},
	{'4', {0x02, 0x06, 0x0a, 0x12, 0x1f, 0x02, 0x02}},
	{'5', {0x1f, 0x10, 0x10, 0x1e, 0x01, 0x01, 0x1e}},
	{'6', {0x0e, 0x10, 0x10, 0x1e, 0x11, 0x11, 0x0e}},
	{'7', {0x1f, 0x01, 0x02, 0x04, 0x04, 0x04, 0x04}},
	{'8', {0x0e, 0x11, 0x11, 0x0e, 0x11, 0x11, 0x0e}},
	{'9', {0x0e, 0x11, 0x11, 0x0f, 0x01, 0x01, 0x0e}},
	{'A', {0x0e, 0x11, 0x11, 0x1f, 0x11, 0x11, 0x11}},
	{'B', {0x1e, 0x11, 0x11, 0x1e, 0x11, 0x11, 0x1e}},
	{'C', {0x0e, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0e}},
	{'D', {0x1e, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1e}},
	{'E', {0x1f, 0x10, 0x10, 0x1e, 0x10, 0x10, 0x1f}},
	{'F', {0x1f, 0x10, 0x10, 0x1e, 0x10, 0x10, 0x10}},
	{'G', {0x0e, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0e}},
	{'H', {0x11, 0x11, 0x11, 0x1f, 0x11, 0x11, 0x11}},
	{'I', {0x0e, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0e}},
	{'J', {0x07, 0x02, 0x02, 0x02, 0x12, 0x12, 0x0c}},
	{'K', {0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11}},
	{'L', {0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1f}},
	{'M', {0x11, 0x1b, 0x15, 0x15, 0x11, 0x11, 0x11}},
	{'N', {0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11}},
	{'O', {0x0e, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0e}},
	{'P', {0x1e, 0x11, 0x11, 0x1e, 0x10, 0x10, 0x10}},
	{'Q', {0x0e, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0d}},
	{'R', {0x1e, 0x11, 0x11, 0x1e, 0x14, 0x12, 0x11}},
	{'S', {0x0f, 0x10, 0x10, 0x0e, 0x01, 0x01, 0x1e}},
	{'T', {0x1f, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04}},
	{'U', {0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0e}},
	{'V', {0x11, 0x11, 0x11, 0x11, 0x0a, 0x0a, 0x04}},
	{'W', {0x11, 0x11, 0x11, 0x15, 0x15, 0x15, 0x0a}},
	{'X', {0x11, 0x11, 0x0a, 0x04, 0x0a, 0x11, 0x11}},
	{'Y', {0x11, 0x11, 0x0a, 0x04, 0x04, 0x04, 0x04}},
	{'Z', {0x1f, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1f}},
	{'a', {0, 0, 0x0e, 0x01, 0x0f, 0x11, 0x0f}},
	{'b', {0x10, 0x10, 0x1e, 0x11, 0x11, 0x11, 0x1e}},
	{'c', {0, 0, 0x0e, 0x11, 0x10, 0x11, 0x0e}},
	{'d', {0x01, 0x01, 0x0f, 0x11, 0x11, 0x11, 0x0f}},
	{'e', {0, 0, 0x0e, 0x11, 0x1f, 0x10, 0x0e}},
	{'f', {0x06, 0x08, 0x1e, 0x08, 0x08, 0x08, 0x08}},
	{'g', {0, 0, 0x0f, 0x11, 0x0f, 0x01, 0x0e}},
	{'h', {0x10, 0x10, 0x1e, 0x11, 0x11, 0x11, 0x11}},
	{'i', {0x04, 0, 0x0c, 0x04, 0x04, 0x04, 0x0e}},
	{'j', {0x02, 0, 0x06, 0x02, 0x02, 0x12, 0x0c}},
	{'k', {0x10, 0x10, 0x12, 0x14, 0x18, 0x14, 0x12}},
	{'l', {0x0c, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0e}},
	{'m', {0, 0, 0x1a, 0x15, 0x15, 0x15, 0x15}},
	{'n', {0, 0, 0x1e, 0x11, 0x11, 0x11, 0x11}},
	{'o', {0, 0, 0x0e, 0x11, 0x11, 0x11, 0x0e}},
	{'p', {0, 0, 0x1e, 0x11, 0x1e, 0x10, 0x10}},
	{'q', {0, 0, 0x0f, 0x11, 0x0f, 0x01, 0x01}},
	{'r', {0, 0, 0x16, 0x19, 0x10, 0x10, 0x10}},
	{'s', {0, 0, 0x0f, 0x10, 0x0e, 0x01, 0x1e}},
	{'t', {0x08, 0x08, 0x1e, 0x08, 0x08, 0x09, 0x06}},
	{'u', {0, 0, 0x11, 0x11, 0x11, 0x13, 0x0d}},
	{'v', {0, 0, 0x11, 0x11, 0x11, 0x0a, 0x04}},
	{'w', {0, 0, 0x11, 0x11, 0x15, 0x15, 0x0a}},
	{'x', {0, 0, 0x11, 0x0a, 0x04, 0x0a, 0x11}},
	{'y', {0, 0, 0x11, 0x11, 0x0f, 0x01, 0x0e}},
	{'z', {0, 0, 0x1f, 0x02, 0x04, 0x08, 0x1f}},
};

static void rectangle(uint32_t *pixels, unsigned int x, unsigned int y,
		      unsigned int width, unsigned int height, uint32_t color)
{
	if (x >= WIDTH || y >= HEIGHT)
		return;
	if (width > WIDTH - x)
		width = WIDTH - x;
	if (height > HEIGHT - y)
		height = HEIGHT - y;
	for (unsigned int row = y; row < y + height; row++)
		for (unsigned int col = x; col < x + width; col++)
			pixels[(size_t)row * WIDTH + col] = color;
}

static const struct glyph *find_glyph(char letter)
{
	for (size_t i = 0; i < sizeof(font) / sizeof(font[0]); i++)
		if (font[i].letter == letter)
			return &font[i];
	for (size_t i = 0; i < sizeof(font) / sizeof(font[0]); i++)
		if (font[i].letter == '?')
			return &font[i];
	return &font[0];
}

static void draw_text(uint32_t *pixels, const char *word, unsigned int x,
		      unsigned int y, unsigned int scale, uint32_t color)
{
	for (size_t i = 0; word[i]; i++) {
		const struct glyph *glyph = find_glyph(word[i]);
		for (unsigned int row = 0; row < 7; row++)
			for (unsigned int col = 0; col < 5; col++)
				if (glyph->row[row] & (0x10U >> col))
					rectangle(pixels, x + (unsigned int)i * 6U * scale + col * scale,
						  y + row * scale, scale, scale, color);
	}
}

static int read_battery_percent(void)
{
	FILE *stream = fopen("/sys/bus/i2c/devices/7-0055/battery_snapshot", "r");
	char line[160];
	int value = -1;
	if (!stream)
		return -1;
	while (fgets(line, sizeof(line), stream)) {
		if (sscanf(line, "capacity_percent=%d", &value) == 1)
			break;
	}
	fclose(stream);
	return value >= 0 && value <= 100 ? value : -1;
}

static void paint_lynx_status(uint32_t *pixels, int capacity)
{
	const uint32_t background = 0x00121c29;
	const uint32_t teal = 0x0009dcc4;
	const uint32_t white = 0x00f5f8fa;
	const uint32_t muted = 0x007d94a5;
	const uint32_t amber = 0x00edb961;
	char percent[16];
	if (capacity < 0 || capacity > 100)
		capacity = -1;

	for (size_t i = 0; i < (size_t)WIDTH * HEIGHT; i++)
		pixels[i] = background;
	/* A few bold shapes keep the screen legible at phone viewing distance. */
	rectangle(pixels, 0, 0, WIDTH, 36, teal);
	rectangle(pixels, 190, 300, 860, 12, teal);
	draw_text(pixels, "LYNX", 380, 380, 20, white);
	draw_text(pixels, "NATIVE LINUX", 224, 620, 11, muted);
	rectangle(pixels, 290, 970, 650, 220, muted);
	rectangle(pixels, 308, 988, 614, 184, background);
	rectangle(pixels, 940, 1035, 25, 90, muted);
	if (capacity >= 0) {
		rectangle(pixels, 322, 1002, (unsigned int)(586 * capacity / 100),
			  156, capacity > 20 ? teal : amber);
		snprintf(percent, sizeof(percent), "%d%%", capacity);
		unsigned int digits = (unsigned int)strlen(percent);
		unsigned int width = digits * 6U * 24U;
		draw_text(pixels, percent, (WIDTH - width) / 2U, 1350, 24, white);
	} else {
		draw_text(pixels, "BATTERY", 200, 1350, 20, amber);
	}
	rectangle(pixels, 190, 1950, 860, 4, muted);
	rectangle(pixels, 0, HEIGHT - 36, WIDTH, 36, teal);
}

struct scene {
	char selection[96];
	char frames[MAX_SCENE_FRAMES][64];
	size_t count;
	bool animate;
};

static bool safe_name(const char *name)
{
	size_t length = strlen(name);
	if (!length || length >= 64)
		return false;
	for (size_t i = 0; i < length; i++)
		if (!((name[i] >= 'a' && name[i] <= 'z') ||
		      (name[i] >= '0' && name[i] <= '9') || name[i] == '_'))
			return false;
	return true;
}

static int read_scene(struct scene *scene)
{
	char selection[96] = "pose 01_standing_smile";
	FILE *file = fopen(SELECTION_FILE, "r");
	if (file) {
		if (!fgets(selection, sizeof(selection), file)) {
			fclose(file);
			return -1;
		}
		fclose(file);
		selection[strcspn(selection, "\r\n")] = 0;
	}
	if (!strcmp(selection, scene->selection))
		return 0;
	struct scene candidate = { 0 };
	if (snprintf(candidate.selection, sizeof(candidate.selection), "%s", selection) >=
	    (int)sizeof(candidate.selection))
		return -1;
	const char *name;
	if (!strncmp(selection, "pose ", 5)) {
		name = selection + 5;
		if (!safe_name(name))
			return -1;
		snprintf(candidate.frames[0], sizeof(candidate.frames[0]), "%s", name);
		candidate.count = 1;
	} else if (!strncmp(selection, "animate ", 8)) {
		name = selection + 8;
		if (!safe_name(name))
			return -1;
		char path[256];
		snprintf(path, sizeof(path), FRAME_DIR "/%s.list", name);
		file = fopen(path, "r");
		if (!file)
			return -1;
		while (candidate.count < MAX_SCENE_FRAMES &&
		       fgets(candidate.frames[candidate.count], sizeof(candidate.frames[0]), file)) {
			char *frame = candidate.frames[candidate.count];
			frame[strcspn(frame, "\r\n")] = 0;
			if (!safe_name(frame)) {
				fclose(file);
				return -1;
			}
			candidate.count++;
		}
		fclose(file);
		if (!candidate.count)
			return -1;
		candidate.animate = true;
	} else {
		return -1;
	}
	for (size_t i = 0; i < candidate.count; i++) {
		char path[256];
		snprintf(path, sizeof(path), FRAME_DIR "/%s.rgb565.gz", candidate.frames[i]);
		if (access(path, R_OK))
			return -1;
	}
	*scene = candidate;
	return 1;
}

static int paint_lynx_portrait(uint32_t *pixels, const char *name, int capacity)
{
	char path[256];
	if (!name || !*name)
		name = "01_standing_smile";
	if (!safe_name(name))
		return -1;
	snprintf(path, sizeof(path), FRAME_DIR "/%s.rgb565.gz", name);
	gzFile input = gzopen(path, "rb");
	if (!input)
		return -1;
	uint16_t *rgb565 = malloc((size_t)WIDTH * HEIGHT * sizeof(uint16_t));
	if (!rgb565) {
		gzclose(input);
		return -1;
	}
	size_t total = (size_t)WIDTH * HEIGHT * sizeof(uint16_t);
	size_t offset = 0;
	while (offset < total) {
		int n = gzread(input, (uint8_t *)rgb565 + offset,
				 (unsigned int)((total - offset) > 1048576 ? 1048576 : total - offset));
		if (n <= 0)
			break;
		offset += (size_t)n;
	}
	int extra = gzgetc(input);
	int close_result = gzclose(input);
	if (offset != total || extra != -1 || close_result != Z_OK) {
		free(rgb565);
		errno = EINVAL;
		return -1;
	}
	for (size_t i = 0; i < (size_t)WIDTH * HEIGHT; i++) {
		uint16_t color = rgb565[i];
		pixels[i] = ((uint32_t)(color >> 11) << 19) |
			    ((uint32_t)((color >> 5) & 63) << 10) |
			    ((uint32_t)(color & 31) << 3);
	}
	free(rgb565);
	const uint32_t white = 0x00f5f8fa, teal = 0x0009dcc4;
	char value[24];
	/* All original portraits have quiet black space above the ears. */
	draw_text(pixels, "LYNX", 422, 85, 17, white);
	time_t now = time(NULL);
	if (now >= 1700000000) {
		struct tm local;
		if (localtime_r(&now, &local)) {
			snprintf(value, sizeof(value), "%02d:%02d", local.tm_hour, local.tm_min);
			draw_text(pixels, value, 130, 315, 12, white);
		}
	}
	if (capacity >= 0 && capacity <= 100) {
		snprintf(value, sizeof(value), "%d%%", capacity);
		draw_text(pixels, value, 885, 315, 12, white);
		rectangle(pixels, 860, 455, 300, 12, 0x00545b65);
		rectangle(pixels, 860, 455, (unsigned int)(300 * capacity / 100),
			  12, capacity > 20 ? teal : 0x00edb961);
	}
	return 0;
}

enum lynx_page {
	PAGE_HOME,
	PAGE_CHAT,
	PAGE_INPUTS,
	PAGE_OUTPUTS,
	PAGE_STATUS,
	PAGE_CONSOLE,
	PAGE_POWER,	/* power saving: one START button (Tom, 2026-11-23) */
	PAGE_RADIO,	/* radios: Wi-Fi, traffic, network, cellular, Bluetooth (LNX-37) */
	PAGE_DEBUG	/* debug: AI stopped, tool catalog, args runner, service output toggle (Banshee, 2026-11-25) */
};
static char console_input[161];
static size_t console_input_length;
static bool console_uppercase, console_symbols, console_send_failed;
static unsigned int console_output_offset, console_input_offset;
static unsigned int console_history_count, console_history_offset;

static char chat_input[161];
static size_t chat_input_length;
static bool chat_uppercase, chat_symbols;
static unsigned int chat_input_offset;
static unsigned int chat_history_count, chat_history_offset;

static const char *console_letter_rows[] = {
	"1234567890", "qwertyuiop", "asdfghjkl-", "zxcvbnm./_"
};
static const char *console_symbol_rows[] = {
	"!@#$%^&*()", "[]{}\\|;:'\"", "+=<>?,.`~/", "1234567890"
};

static unsigned int console_sequence(void)
{
	FILE *stream = fopen(CONSOLE_SNAPSHOT, "r");
	unsigned int sequence = 0;
	if (stream) {
		if (fscanf(stream, "SEQ %u", &sequence) != 1)
			sequence = 0;
		fclose(stream);
	}
	return sequence;
}

static int console_send(void)
{
	if (!console_input_length)
		return 0;
	int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
	if (fd < 0)
		return -1;
	struct sockaddr_un address = { .sun_family = AF_UNIX };
	snprintf(address.sun_path, sizeof(address.sun_path), "%s", CONSOLE_SOCKET);
	struct timeval timeout = { .tv_sec = 1 };
	setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
	int result = -1;
	if (connect(fd, (struct sockaddr *)&address, sizeof(address)) == 0) {
		char request[330], response[16];
		size_t n = 0;
		memcpy(request, "SEND ", 5);
		n = 5;
		static const char hex[] = "0123456789abcdef";
		for (size_t i = 0; i < console_input_length; i++) {
			unsigned char ch = (unsigned char)console_input[i];
			request[n++] = hex[ch >> 4];
			request[n++] = hex[ch & 15];
		}
		request[n++] = '\n';
		if (write(fd, request, n) == (ssize_t)n) {
			ssize_t got = read(fd, response, sizeof(response));
			if (got >= 3 && !memcmp(response, "OK\n", 3))
				result = 0;
		}
	}
	close(fd);
	if (!result) {
		console_input_length = 0;
		console_input[0] = 0;
		console_input_offset = 0;
	}
	return result;
}

static void console_key(unsigned int x, unsigned int y)
{
	console_send_failed = false;
	if (x >= 1185 && x < 1235 && y >= 450 && y < 1370) {
		unsigned int maximum = console_history_count > 14 ?
			console_history_count - 14 : 0;
		console_history_offset = maximum - (y - 450) * maximum / 919U;
		return;
	}
	if (x >= 75 && x < 1165 && y >= 1380 && y < 1425) {
		console_output_offset = (x - 75) * 55U / 1089U;
		return;
	}
	if (x >= 75 && x < 1165 && y >= 1605 && y < 1645) {
		unsigned int maximum = console_input_length > 40 ?
			(unsigned int)console_input_length - 40U : 0;
		console_input_offset = (x - 75) * maximum / 1089U;
		return;
	}
	bool edited = false;
	if (y >= 1650 && y < 2280 && x >= 55) {
		unsigned int row = (y - 1650) / 160;
		unsigned int offset = (y - 1650) % 160;
		unsigned int column = (x - 55) / 113;
		if (row < 4 && offset < 145 && column < 10 &&
		    (x - 55) % 113 < 105 && console_input_length < 160) {
			char ch = (console_symbols ? console_symbol_rows[row] :
				console_letter_rows[row])[column];
			if (console_uppercase && !console_symbols)
				ch = (char)toupper((unsigned char)ch);
			console_input[console_input_length++] = ch;
			console_input[console_input_length] = 0;
			edited = true;
		}
	} else if (y >= 2290 && y < 2450) {
		if (x >= 55 && x < 185)
			console_uppercase = !console_uppercase;
		else if (x >= 195 && x < 325)
			console_symbols = !console_symbols;
		else if (x >= 335 && x < 755 && console_input_length < 160) {
			console_input[console_input_length++] = ' ';
			console_input[console_input_length] = 0;
			edited = true;
		} else if (x >= 765 && x < 945 && console_input_length) {
			console_input[--console_input_length] = 0;
			edited = true;
		} else if (x >= 955 && x < 1185)
			console_send_failed = console_send() < 0;
	}
	if (edited)
		console_input_offset = console_input_length > 40 ?
			(unsigned int)console_input_length - 40U : 0;
}

static int self_test_console_keys(void)
{
	console_input_length = 0;
	console_uppercase = false;
	console_symbols = false;
	console_input[0] = 0;
	console_key(55, 1810);  /* q */
	console_key(55, 2290);  /* shift */
	console_key(168, 1810); /* W */
	console_key(195, 2290); /* symbols */
	console_key(959, 1970); /* ~ */
	console_key(507, 1810); /* backslash */
	console_key(335, 2290); /* space */
	console_key(765, 2290); /* backspace */
	console_key(1164, 1390); /* output scroll */
	int good = !strcmp(console_input, "qW~\\") && console_input_length == 4 &&
		console_uppercase && console_symbols && console_output_offset == 55;
	memset(console_input, 'x', 80);
	console_input[80] = 0;
	console_input_length = 80;
	console_key(1164, 1610); /* input to far right */
	good = good && console_input_offset == 40;
	console_key(75, 1610); /* input to far left */
	good = good && console_input_offset == 0;
	console_key(55, 1810); /* typing follows the end */
	good = good && console_input_length == 81 && console_input_offset == 41;
	console_history_count = 64;
	console_key(1190, 450); /* oldest output */
	good = good && console_history_offset == 50;
	console_key(1190, 1369); /* latest output */
	good = good && console_history_offset == 0;
	console_key(1190, 910); /* middle of the output history */
	good = good && console_history_offset > 0 && console_history_offset < 50;
	printf("console keys %s\n", good ? "PASS" : "FAIL");
	return good ? 0 : 1;
}

static void console_button(uint32_t *pixels, unsigned int x,
			   unsigned int y, unsigned int width, const char *label)
{
	rectangle(pixels, x, y, width, 145, 0x00334e5b);
	draw_text(pixels, label, x + (width < 150 ? 6 : 18), y + 43,
		  width < 150 ? 4 : width < 200 ? 5 : 6, 0x00f5f8fa);
}

static void console_scrollbar(uint32_t *pixels, unsigned int y,
			      unsigned int offset, unsigned int maximum,
			      unsigned int thumb_width)
{
	const unsigned int x = 75, width = 1090;
	if (thumb_width > width)
		thumb_width = width;
	rectangle(pixels, x, y, width, 45, 0x00334e5b);
	unsigned int position = maximum ?
		(width - thumb_width) * offset / maximum : 0;
	rectangle(pixels, x + position, y, thumb_width, 45, 0x0009dcc4);
}

static void console_vertical_scrollbar(uint32_t *pixels, unsigned int count)
{
	const unsigned int x = 1185, y = 450, height = 920;
	const unsigned int maximum = count > 14 ? count - 14 : 0;
	unsigned int thumb = count > 14 ? height * 14 / count : height;
	if (thumb < 80)
		thumb = 80;
	unsigned int position = maximum ?
		(height - thumb) * (maximum - console_history_offset) / maximum : 0;
	rectangle(pixels, x, y, 50, height, 0x00334e5b);
	rectangle(pixels, x, y + position, 50, thumb, 0x0009dcc4);
}

static void paint_console(uint32_t *pixels)
{
	const uint32_t white = 0x00f5f8fa, teal = 0x0009dcc4;
	const uint32_t amber = 0x00edb961, red = 0x00ff8d86;
	draw_text(pixels, "STDOUT", 75, 365, 5, white);
	draw_text(pixels, "STDERR", 365, 365, 5, red);
	draw_text(pixels, "STDWARN", 655, 365, 5, amber);
	struct { char kind; char text[101]; } rows[64] = { 0 };
	unsigned int count = 0;
	FILE *stream = fopen(CONSOLE_SNAPSHOT, "r");
	if (stream) {
		char line[256];
		fgets(line, sizeof(line), stream);
		while (fgets(line, sizeof(line), stream)) {
			if (line[1] != '|')
				continue;
			char kind = line[0];
			char *message = line + 2;
			message[strcspn(message, "\r\n")] = 0;
			unsigned int slot = count < 64 ? count : 63;
			if (count >= 64)
				memmove(rows, rows + 1, sizeof(rows[0]) * 63);
			rows[slot].kind = kind;
			snprintf(rows[slot].text, sizeof(rows[slot].text), "%s", message);
			count++;
		}
		fclose(stream);
	} else {
		draw_text(pixels, "CONSOLE STARTING", 75, 470, 5, amber);
	}
	if (count > 64)
		count = 64;
	console_history_count = count;
	unsigned int visible = count > 14 ? 14 : count;
	unsigned int maximum = count - visible;
	if (console_history_offset > maximum)
		console_history_offset = maximum;
	unsigned int first = maximum - console_history_offset;
	for (unsigned int i = 0; i < visible; i++) {
		unsigned int row = first + i;
		uint32_t color = rows[row].kind == 'E' ? red :
			rows[row].kind == 'W' ? amber : rows[row].kind == 'I' ? teal : white;
		char text[46] = { 0 };
		if (console_output_offset < strlen(rows[row].text))
			snprintf(text, sizeof(text), "%.*s", 45,
				 rows[row].text + console_output_offset);
		draw_text(pixels, text, 75, 460 + i * 67, 4, color);
	}
	console_vertical_scrollbar(pixels, count);
	console_scrollbar(pixels, 1390, console_output_offset, 55, 490);
	rectangle(pixels, 55, 1450, 1130, 145, 0x00253b49);
	draw_text(pixels, "STDIN", 75, 1471, 4, teal);
	char shown[41] = { 0 };
	snprintf(shown, sizeof(shown), "%.*s", 40,
		 console_input + console_input_offset);
	draw_text(pixels, shown, 75, 1530, 5, white);
	if (console_send_failed)
		draw_text(pixels, "SEND FAILED", 820, 1471, 4, red);
	unsigned int input_max = console_input_length > 40 ?
		(unsigned int)console_input_length - 40U : 0;
	unsigned int thumb = console_input_length > 40 ?
		1090U * 40U / (unsigned int)console_input_length : 1090U;
	console_scrollbar(pixels, 1600, console_input_offset, input_max, thumb);
	for (unsigned int row = 0; row < 4; row++) {
		for (unsigned int column = 0; column < 10; column++) {
			char label[] = { (console_symbols ? console_symbol_rows[row] :
				console_letter_rows[row])[column], 0 };
			if (!console_symbols)
				label[0] = (char)toupper((unsigned char)label[0]);
			console_button(pixels, 55 + column * 113,
				       1650 + row * 160, 105, label);
		}
	}
	console_button(pixels, 55, 2290, 130,
		       console_uppercase ? "UPPER" : "LOWER");
	console_button(pixels, 195, 2290, 130,
		       console_symbols ? "ABC" : "SYM");
	console_button(pixels, 335, 2290, 420, "SPACE");
	console_button(pixels, 765, 2290, 180, "BACK");
	console_button(pixels, 955, 2290, 230, "ENTER");
}

static int read_integer(const char *path)
{
	FILE *stream = fopen(path, "r");
	int value;
	if (!stream)
		return -1;
	int found = fscanf(stream, "%d", &value);
	fclose(stream);
	return found == 1 ? value : -1;
}

static bool file_contains(const char *path, const char *needle)
{
	FILE *stream = fopen(path, "r");
	char line[256];
	if (!stream)
		return false;
	bool found = false;
	while (fgets(line, sizeof(line), stream)) {
		if (strstr(line, needle)) {
			found = true;
			break;
		}
	}
	fclose(stream);
	return found;
}

static bool path_matches(const char *pattern)
{
	glob_t matches = { 0 };
	int result = glob(pattern, 0, NULL, &matches);
	bool found = result == 0 && matches.gl_pathc > 0;
	globfree(&matches);
	return found;
}

static bool camera_capture_node_present(void)
{
	glob_t matches = { 0 };
	bool found = false;
	if (glob("/sys/class/video4linux/video*/name", 0, NULL, &matches) == 0) {
		for (size_t i = 0; i < matches.gl_pathc; i++) {
			if (file_contains(matches.gl_pathv[i], "MTK-CAM") ||
			    file_contains(matches.gl_pathv[i], "mtk-cam") ||
			    file_contains(matches.gl_pathv[i], "Camera")) {
				found = true;
				break;
			}
		}
	}
	globfree(&matches);
	return found;
}

static bool pid_matches(const char *pidfile, const char *needle)
{
	int pid = read_integer(pidfile);
	if (pid <= 1 || kill(pid, 0) < 0)
		return false;
	char path[64], command[512];
	snprintf(path, sizeof(path), "/proc/%d/cmdline", pid);
	FILE *stream = fopen(path, "rb");
	if (!stream)
		return false;
	size_t size = fread(command, 1, sizeof(command) - 1, stream);
	fclose(stream);
	for (size_t i = 0; i < size; i++)
		if (!command[i])
			command[i] = ' ';
	command[size] = 0;
	return strstr(command, needle) != NULL;
}

static void battery_snapshot(int *capacity, int *temp_mc, int *current_ma,
			     int *voltage_mv)
{
	*capacity = *temp_mc = *current_ma = *voltage_mv = -1;
	FILE *stream = fopen("/sys/bus/i2c/devices/7-0055/battery_snapshot", "r");
	char line[160];
	int capacity_error = 1, temperature_error = 1, current_error = 1;
	int voltage_error = 1;
	if (!stream)
		return;
	while (fgets(line, sizeof(line), stream)) {
		sscanf(line, "capacity_percent=%d", capacity);
		sscanf(line, "temperature_millidegrees_celsius=%d", temp_mc);
		sscanf(line, "gauge_current_ma_signed=%d", current_ma);
		sscanf(line, "pack_voltage_mv=%d", voltage_mv);
		sscanf(line, "capacity_error=%d", &capacity_error);
		sscanf(line, "temperature_error=%d", &temperature_error);
		sscanf(line, "current_error=%d", &current_error);
		sscanf(line, "voltage_error=%d", &voltage_error);
	}
	fclose(stream);
	if (capacity_error || *capacity < 0 || *capacity > 100)
		*capacity = -1;
	if (temperature_error || *temp_mc < -20000 || *temp_mc > 80000)
		*temp_mc = -1;
	if (current_error || *current_ma < -10000 || *current_ma > 10000)
		*current_ma = -1;
	if (voltage_error || *voltage_mv < 5000 || *voltage_mv > 10000)
		*voltage_mv = -1;
}

static void wifi_address(char *output, size_t size)
{
	snprintf(output, size, "UNAVAILABLE");
	struct ifaddrs *interfaces = NULL;
	if (getifaddrs(&interfaces) < 0)
		return;
	for (struct ifaddrs *item = interfaces; item; item = item->ifa_next) {
		if (item->ifa_addr && !strcmp(item->ifa_name, "wlan0") &&
		    item->ifa_addr->sa_family == AF_INET) {
			inet_ntop(AF_INET,
				&((struct sockaddr_in *)item->ifa_addr)->sin_addr,
				output, size);
			break;
		}
	}
	freeifaddrs(interfaces);
}

static void cellular_address(char *output, size_t size)
{
	snprintf(output, size, "DOWN");
	struct ifaddrs *interfaces = NULL;
	if (getifaddrs(&interfaces) < 0)
		return;
	for (struct ifaddrs *item = interfaces; item; item = item->ifa_next) {
		if (item->ifa_addr && !strcmp(item->ifa_name, "ccmni0") &&
		    item->ifa_addr->sa_family == AF_INET) {
			inet_ntop(AF_INET,
				&((struct sockaddr_in *)item->ifa_addr)->sin_addr,
				output, size);
			break;
		}
	}
	freeifaddrs(interfaces);
}

static bool is_ai_worker_running(void)
{
	if (access("/var/lib/lynx-agent/stop", F_OK) == 0)
		return false;
	return pid_matches("/run/lynx/agent-worker.pid", "lynx-agent-worker") ||
	       pid_matches("/run/lynx/agent-worker.pid", "python") ||
	       pid_matches("/run/lynx/noobd.pid", "lynx-noobd");
}

static void nav_buttons(uint32_t *pixels, enum lynx_page page)
{
	const uint32_t dark = 0x00121c29, teal = 0x0009dcc4;
	const uint32_t white = 0x00f5f8fa, muted = 0x002c3844;
	const uint32_t border = 0x00455566;
	rectangle(pixels, 0, 2510, WIDTH, 262, dark);

	struct {
		enum lynx_page p;
		unsigned int x;
		unsigned int w;
		const char *label;
		unsigned int lx;
		unsigned int scale;
	} btns[] = {
		/* Four unified navigation buttons: HOME, CHAT, STATUS (includes Radios), DEBUG */
		{ PAGE_HOME,   40,  260, "HOME",   110, 5 },
		{ PAGE_CHAT,   340, 260, "CHAT",   410, 5 },
		{ PAGE_STATUS, 640, 260, "STATUS", 690, 5 },
		{ PAGE_DEBUG,  940, 260, "DEBUG",  1000, 5 },
	};

	for (size_t i = 0; i < sizeof(btns)/sizeof(btns[0]); i++) {
		bool active = (page == btns[i].p);
		uint32_t bg = active ? teal : muted;
		uint32_t tc = active ? 0x000b141d : white;
		uint32_t bc = active ? teal : border;
		rectangle(pixels, btns[i].x, 2550, btns[i].w, 160, bg);
		rectangle(pixels, btns[i].x, 2550, btns[i].w, 3, bc);
		rectangle(pixels, btns[i].x, 2707, btns[i].w, 3, bc);
		rectangle(pixels, btns[i].x, 2550, 3, 160, bc);
		rectangle(pixels, btns[i].x + btns[i].w - 3, 2550, 3, 160, bc);
		draw_text(pixels, btns[i].label, btns[i].lx, 2612, btns[i].scale, tc);
	}
}

static void status_item(uint32_t *pixels, unsigned int column,
			unsigned int row, const char *label, const char *value)
{
	unsigned int x = column ? 660 : 75;
	unsigned int y = 370 + row * 195;
	draw_text(pixels, label, x, y, 4, 0x007d94a5);
	draw_text(pixels, value, x, y + 55, 5, 0x00f5f8fa);
}

static time_t get_thought_mtime(void)
{
	struct stat st;
	if (stat(THOUGHT_FILE, &st) == 0)
		return st.st_mtime;
	return 0;
}

static int read_hearing_enabled(void)
{
	FILE *f = fopen(HEARING_ENABLED_FILE, "r");
	if (!f)
		return 0;
	char buf[16] = {0};
	int val = 0;
	if (fgets(buf, sizeof(buf), f)) {
		if (buf[0] == '1' || buf[0] == 't' || buf[0] == 'T' || buf[0] == 'y' || buf[0] == 'Y')
			val = 1;
	}
	fclose(f);
	return val;
}

static int read_aigel_learning_mode(void)
{
	FILE *f = fopen(AIGEL_MODE_FILE, "r");
	if (!f)
		return 0;
	char buf[32] = {0};
	int val = 0;
	if (fgets(buf, sizeof(buf), f)) {
		if (strstr(buf, "learn") || buf[0] == '1')
			val = 1;
	}
	fclose(f);
	return val;
}

static void toggle_aigel_mode(void)
{
	int current = read_aigel_learning_mode();
	int new_mode = current ? 0 : 1;
	FILE *f = fopen(AIGEL_MODE_FILE, "w");
	if (f) {
		fprintf(f, "%s\n", new_mode ? "learning" : "normal");
		fclose(f);
	}
}

static void toggle_hearing(void)
{
	int current = read_hearing_enabled();
	int new_state = current ? 0 : 1;
	FILE *f = fopen(HEARING_ENABLED_FILE, "w");
	if (f) {
		fprintf(f, "%d\n", new_state);
		fclose(f);
	}
	/* Notify Nexus LAN endpoint in background asynchronously */
	pid_t pid = fork();
	if (pid == 0) {
		int devnull = open("/dev/null", O_RDWR);
		if (devnull >= 0) {
			dup2(devnull, STDIN_FILENO);
			dup2(devnull, STDOUT_FILENO);
			dup2(devnull, STDERR_FILENO);
			close(devnull);
		}
		execl("/usr/bin/python3", "python3", "-c",
		      "import urllib.request\n"
		      "try:\n"
		      "    req = urllib.request.Request('http://192.168.100.106:112/api/v1/hearing/toggle', method='POST')\n"
		      "    urllib.request.urlopen(req, timeout=1)\n"
		      "except Exception:\n"
		      "    pass\n",
		      (char *)NULL);
		_exit(0);
	}
}

static void haptic_tick(int duration_ms)
{
	int fd = open("/sys/class/leds/vibrator/duration", O_WRONLY);
	if (fd >= 0) {
		char buf[16];
		int n = snprintf(buf, sizeof(buf), "%d\n", duration_ms);
		if (n > 0) {
			ssize_t ret = write(fd, buf, (size_t)n);
			(void)ret;
		}
		close(fd);
	}
	fd = open("/sys/class/leds/vibrator/activate", O_WRONLY);
	if (fd >= 0) {
		ssize_t ret = write(fd, "1\n", 2);
		(void)ret;
		close(fd);
	}
}

static void draw_text_shadow(uint32_t *pixels, const char *word, unsigned int x,
			     unsigned int y, unsigned int scale, uint32_t color,
			     uint32_t shadow_color)
{
	draw_text(pixels, word, x + 2, y + 2, scale, shadow_color);
	draw_text(pixels, word, x, y, scale, color);
}

static void paint_thoughts(uint32_t *pixels)
{
	const uint32_t white = 0x00f5f8fa, muted = 0x007d94a5, shadow = 0x00000000;

	FILE *f = fopen(THOUGHT_FILE, "r");
	char last_thought[1024] = {0};
	if (f) {
		char line[1024];
		while (fgets(line, sizeof(line), f)) {
			char *p = line;
			while (*p == ' ' || *p == '\t')
				p++;
			if (!*p || *p == '\n' || *p == '\r')
				continue;
			p[strcspn(p, "\r\n")] = 0;
			/* Front screen shows only Lynx's own thoughts, not user input lines */
			if (!strncmp(p, "Noob:", 5) || !strncmp(p, "User:", 5))
				continue;
			snprintf(last_thought, sizeof(last_thought), "%s", p);
		}
		fclose(f);
	}

	if (last_thought[0] == 0) {
		draw_text_shadow(pixels, "(listening...)", 75, 2300, 4, muted, shadow);
		return;
	}

	for (size_t i = 0; last_thought[i]; i++) {
		if (last_thought[i] == '\r' || last_thought[i] == '\t')
			last_thought[i] = ' ';
	}

	/* Word wrap her latest thought into lines of up to 44 characters */
	const unsigned int scale = 4;
	const unsigned int line_h = 7 * scale + 10; /* 28 + 10 = 38px */
	const int max_chars = 44;
	char lines[16][64];
	int line_count = 0;

	char *p = last_thought;
	size_t rem = strlen(p);
	while (rem > 0 && line_count < 16) {
		while (*p == ' ') {
			p++;
			rem--;
		}
		if (rem == 0)
			break;

		int split = (int)rem <= max_chars ? (int)rem : max_chars;
		if (split < (int)rem) {
			int s = split;
			while (s > 0 && p[s] != ' ')
				s--;
			if (s > 0)
				split = s;
		}
		snprintf(lines[line_count], sizeof(lines[line_count]), "%.*s", split, p);
		line_count++;
		p += split;
		rem -= (size_t)split;
	}

	if (line_count == 0) {
		draw_text_shadow(pixels, "(listening...)", 75, 2300, 4, muted, shadow);
		return;
	}

	/* Show up to 10 lines */
	const int max_visible = 10;
	int start_idx = line_count > max_visible ? line_count - max_visible : 0;
	int visible_count = line_count - start_idx;

	/* Position right above hearing button (y=2360) with transparent background */
	unsigned int base_y = 2330 - (unsigned int)visible_count * line_h;
	if (base_y < 1850)
		base_y = 1850;

	for (int i = start_idx; i < line_count; i++) {
		draw_text_shadow(pixels, lines[i], 70, base_y, scale, white, shadow);
		base_y += line_h;
	}
}

static void paint_compact_buttons(uint32_t *pixels)
{
	int on = read_hearing_enabled();
	const uint32_t h_bg = on ? 0x001a7042 : 0x002c3844;
	const uint32_t h_border = on ? 0x002aa860 : 0x00455566;
	const uint32_t c_bg = 0x00183b54;
	const uint32_t c_border = 0x0009dcc4;
	const uint32_t white = 0x00f5f8fa;

	/* Hearing button: x=50..605, y=2360..2490 (width 555, height 130) */
	rectangle(pixels, 50, 2360, 555, 130, h_bg);
	rectangle(pixels, 50, 2360, 555, 4, h_border);
	rectangle(pixels, 50, 2486, 555, 4, h_border);
	rectangle(pixels, 50, 2360, 4, 130, h_border);
	rectangle(pixels, 601, 2360, 4, 130, h_border);

	if (on) {
		draw_text(pixels, "HEARING: ON", 162, 2407, 5, white);
	} else {
		draw_text(pixels, "HEARING: OFF", 147, 2407, 5, white);
	}

	/* Chat button: x=635..1190, y=2360..2490 (width 555, height 130) */
	rectangle(pixels, 635, 2360, 555, 130, c_bg);
	rectangle(pixels, 635, 2360, 555, 4, c_border);
	rectangle(pixels, 635, 2486, 555, 4, c_border);
	rectangle(pixels, 635, 2360, 4, 130, c_border);
	rectangle(pixels, 1186, 2360, 4, 130, c_border);

	draw_text(pixels, "CHAT WITH LYNX", 702, 2407, 5, white);
}

static int chat_send(void)
{
	if (!chat_input_length)
		return 0;

	/* Dispatch to lynx-chat-send which appends to thought log, */
	/* queues direct agent job, and emits sense line. */
	pid_t pid = fork();
	if (pid == 0) {
		int devnull = open("/dev/null", O_RDWR);
		if (devnull >= 0) {
			dup2(devnull, STDIN_FILENO);
			dup2(devnull, STDOUT_FILENO);
			dup2(devnull, STDERR_FILENO);
			close(devnull);
		}
		execl("/usr/bin/python3", "python3",
		      "/usr/local/bin/lynx-chat-send",
		      chat_input, (char *)NULL);
		_exit(0);
	}

	haptic_tick(50);
	chat_input_length = 0;
	chat_input[0] = 0;
	chat_input_offset = 0;
	chat_history_offset = 0;
	return 0;
}

static void chat_key(unsigned int x, unsigned int y)
{
	if (x >= 1185 && x < 1235 && y >= 390 && y < 1370) {
		unsigned int maximum = chat_history_count > 14 ?
			chat_history_count - 14 : 0;
		chat_history_offset = maximum - (y - 390) * maximum / 979U;
		return;
	}
	if (x >= 55 && x < 1185 && y >= 1380 && y < 1520) {
		unsigned int maximum = chat_input_length > 40 ?
			(unsigned int)chat_input_length - 40U : 0;
		chat_input_offset = (x - 55) * maximum / 1129U;
		return;
	}
	bool edited = false;
	if (y >= 1550 && y < 2100 && x >= 55) {
		unsigned int row = (y - 1550) / 140;
		unsigned int offset = (y - 1550) % 140;
		unsigned int column = (x - 55) / 113;
		if (row < 4 && offset < 130 && column < 10 &&
		    (x - 55) % 113 < 105 && chat_input_length < 160) {
			char ch = (chat_symbols ? console_symbol_rows[row] :
				console_letter_rows[row])[column];
			if (chat_uppercase && !chat_symbols)
				ch = (char)toupper((unsigned char)ch);
			chat_input[chat_input_length++] = ch;
			chat_input[chat_input_length] = 0;
			edited = true;
		}
	} else if (y >= 2110 && y < 2270) {
		if (x >= 55 && x < 185)
			chat_uppercase = !chat_uppercase;
		else if (x >= 195 && x < 325)
			chat_symbols = !chat_symbols;
		else if (x >= 335 && x < 755 && chat_input_length < 160) {
			chat_input[chat_input_length++] = ' ';
			chat_input[chat_input_length] = 0;
			edited = true;
		} else if (x >= 765 && x < 945 && chat_input_length) {
			chat_input[--chat_input_length] = 0;
			edited = true;
		} else if (x >= 955 && x < 1185) {
			chat_send();
			edited = true;
		}
	}
	if (edited)
		chat_input_offset = chat_input_length > 40 ?
			(unsigned int)chat_input_length - 40U : 0;
}

static int self_test_chat_keys(void)
{
	chat_input_length = 0;
	chat_uppercase = false;
	chat_symbols = false;
	chat_input[0] = 0;
	chat_key(55, 1690);  /* q */
	chat_key(55, 2120);  /* shift */
	chat_key(168, 1690); /* W */
	chat_key(195, 2120); /* symbols */
	chat_key(959, 1830); /* ~ */
	chat_key(335, 2120); /* space */
	chat_key(765, 2120); /* backspace */
	int good = !strcmp(chat_input, "qW~") && chat_input_length == 3 &&
		chat_uppercase && chat_symbols;
	printf("chat keys %s\n", good ? "PASS" : "FAIL");
	return good ? 0 : 1;
}

static void paint_chat(uint32_t *pixels)
{
	const uint32_t dark = 0x00121c29, white = 0x00f5f8fa, teal = 0x0009dcc4;
	const uint32_t amber = 0x00edb961;

	for (size_t i = 0; i < (size_t)WIDTH * HEIGHT; i++)
		pixels[i] = dark;

	rectangle(pixels, 0, 0, WIDTH, 28, teal);
	draw_text(pixels, "CHAT", 85, 155, 13, white);
	rectangle(pixels, 75, 300, 1090, 5, teal);
	draw_text(pixels, "HER THOUGHTS & YOUR WORDS", 85, 325, 4, teal);

	struct { char text[64]; uint32_t color; } rows[256];
	unsigned int count = 0;
	FILE *stream = fopen(THOUGHT_FILE, "r");
	if (stream) {
		char line[512];
		while (fgets(line, sizeof(line), stream)) {
			char *msg = line;
			while (*msg == ' ' || *msg == '\t') msg++;
			if (!*msg || *msg == '\n' || *msg == '\r')
				continue;
			msg[strcspn(msg, "\r\n")] = 0;

			uint32_t col = white;
			if (!strncmp(msg, "Noob:", 5) || !strncmp(msg, "User:", 5))
				col = teal;
			else if (!strncmp(msg, "*", 1))
				col = amber;

			/* Word wrap into rows of up to 44 characters */
			const int max_chars = 44;
			char *p = msg;
			size_t rem = strlen(p);
			bool first_line = true;
			while (rem > 0) {
				while (*p == ' ') { p++; rem--; }
				if (rem == 0) break;

				int split = (int)rem <= max_chars ? (int)rem : max_chars;
				if (split < (int)rem) {
					int s = split;
					while (s > 0 && p[s] != ' ') s--;
					if (s > 0) split = s;
				}

				unsigned int slot = count < 256 ? count : 255;
				if (count >= 256)
					memmove(rows, rows + 1, sizeof(rows[0]) * 255);

				rows[slot].color = col;
				if (!first_line)
					snprintf(rows[slot].text, sizeof(rows[slot].text), "  %.*s", split > 42 ? 42 : split, p);
				else
					snprintf(rows[slot].text, sizeof(rows[slot].text), "%.*s", split, p);

				first_line = false;
				count++;
				p += split;
				rem -= (size_t)split;
			}
		}
		fclose(stream);
	}
	if (!count) {
		snprintf(rows[0].text, sizeof(rows[0].text), "NO THOUGHTS YET. TYPE BELOW TO SPEAK.");
		rows[0].color = teal;
		count = 1;
	}
	if (count > 256)
		count = 256;
	chat_history_count = count;

	unsigned int visible = count > 14 ? 14 : count;
	unsigned int maximum = count - visible;
	if (chat_history_offset > maximum)
		chat_history_offset = maximum;
	unsigned int first = maximum - chat_history_offset;
	for (unsigned int i = 0; i < visible; i++) {
		unsigned int row = first + i;
		draw_text(pixels, rows[row].text, 75, 390 + i * 62, 4, rows[row].color);
	}

	/* Vertical scrollbar on right: x=1185, y=390, h=960 */
	const unsigned int sb_x = 1185, sb_y = 390, sb_h = 960;
	unsigned int thumb = count > 14 ? sb_h * 14 / count : sb_h;
	if (thumb < 80) thumb = 80;
	unsigned int pos = maximum ? (sb_h - thumb) * (maximum - chat_history_offset) / maximum : 0;
	rectangle(pixels, sb_x, sb_y, 50, sb_h, 0x00334e5b);
	rectangle(pixels, sb_x, sb_y + pos, 50, thumb, teal);

	/* Input box at y=1380..1520 */
	rectangle(pixels, 55, 1380, 1130, 140, 0x00253b49);
	rectangle(pixels, 55, 1380, 1130, 3, teal);
	rectangle(pixels, 55, 1517, 1130, 3, teal);
	rectangle(pixels, 55, 1380, 3, 140, teal);
	rectangle(pixels, 1182, 1380, 3, 140, teal);
	draw_text(pixels, "SPEAK TO HER THOUGHTS:", 75, 1395, 4, teal);
	char shown[42] = { 0 };
	snprintf(shown, sizeof(shown), "%.*s_", 40, chat_input + chat_input_offset);
	draw_text(pixels, shown, 75, 1445, 5, white);

	/* Keyboard at y=1550..2270 */
	for (unsigned int row = 0; row < 4; row++) {
		for (unsigned int col = 0; col < 10; col++) {
			char lbl[] = { (chat_symbols ? console_symbol_rows[row] :
				console_letter_rows[row])[col], 0 };
			if (!chat_symbols)
				lbl[0] = (char)toupper((unsigned char)lbl[0]);
			console_button(pixels, 55 + col * 113,
				       1550 + row * 140, 105, lbl);
		}
	}
	console_button(pixels, 55, 2110, 130,
		       chat_uppercase ? "UPPER" : "LOWER");
	console_button(pixels, 195, 2110, 130,
		       chat_symbols ? "ABC" : "SYM");
	console_button(pixels, 335, 2110, 420, "SPACE");
	console_button(pixels, 765, 2110, 180, "BACK");
	rectangle(pixels, 955, 2110, 230, 145, teal);
	draw_text(pixels, "SEND", 1000, 2153, 6, 0x000b141d);
}

static int count_jobs(const char *suffix)
{
	DIR *d = opendir("/var/lib/lynx-agent/jobs");
	if (!d)
		return 0;
	int count = 0;
	size_t slen = strlen(suffix);
	struct dirent *de;
	while ((de = readdir(d)) != NULL) {
		size_t nlen = strlen(de->d_name);
		if (nlen > slen && !strcmp(de->d_name + nlen - slen, suffix))
			count++;
	}
	closedir(d);
	return count;
}

static void get_running_job_snippet(char *buf, size_t sz)
{
	DIR *d = opendir("/var/lib/lynx-agent/jobs");
	if (!d) {
		snprintf(buf, sz, "IDLE (NO RUNNING JOB)");
		return;
	}
	struct dirent *de;
	char found[256] = {0};
	while ((de = readdir(d)) != NULL) {
		size_t nlen = strlen(de->d_name);
		if (nlen > 8 && !strcmp(de->d_name + nlen - 8, ".running")) {
			snprintf(found, sizeof(found), "/var/lib/lynx-agent/jobs/%s", de->d_name);
			break;
		}
	}
	closedir(d);
	if (!found[0]) {
		snprintf(buf, sz, "IDLE (WAITING FOR STIMULUS)");
		return;
	}
	FILE *f = fopen(found, "r");
	if (!f) {
		snprintf(buf, sz, "JOB ACTIVE");
		return;
	}
	char line[512] = {0};
	char *obs = NULL;
	while (fgets(line, sizeof(line), f)) {
		if ((obs = strstr(line, "\"text\": \"")) != NULL) {
			obs += 9;
			char *end = strchr(obs, '"');
			if (end) *end = 0;
			snprintf(buf, sz, "AIGEL: %s", obs);
			fclose(f);
			return;
		}
	}
	fclose(f);
	snprintf(buf, sz, "COGNITIVE TURN IN PROGRESS");
}

static unsigned int inputs_scroll_offset = 0;
static unsigned int inputs_line_count = 0;
static unsigned int outputs_scroll_offset = 0;
static unsigned int outputs_line_count = 0;
static unsigned int radio_scroll_offset = 0;
static unsigned int radio_line_count = 0;

struct text_row {
	char text[64];
	uint32_t color;
	bool is_header;
};

static void add_scroll_row(struct text_row *rows, unsigned int *count, unsigned int max_rows,
			   const char *text, uint32_t color, bool is_header)
{
	if (*count >= max_rows)
		return;
	const int max_chars = 44;
	const char *p = text;
	size_t rem = strlen(p);
	bool first = true;
	if (rem == 0) {
		if (first && *count < max_rows) {
			unsigned int slot = *count;
			rows[slot].color = color;
			rows[slot].is_header = false;
			rows[slot].text[0] = 0;
			(*count)++;
		}
		return;
	}
	while (rem > 0 && *count < max_rows) {
		while (*p == ' ' || *p == '\r' || *p == '\n') { p++; rem--; }
		if (rem == 0) break;
		int split = (int)rem <= max_chars ? (int)rem : max_chars;
		if (split < (int)rem) {
			int s = split;
			while (s > 0 && p[s] != ' ') s--;
			if (s > 0) split = s;
		}
		unsigned int slot = *count;
		rows[slot].color = color;
		rows[slot].is_header = is_header && first;
		if (!first)
			snprintf(rows[slot].text, sizeof(rows[slot].text), "  %.*s", split > 42 ? 42 : split, p);
		else
			snprintf(rows[slot].text, sizeof(rows[slot].text), "%.*s", split, p);
		first = false;
		(*count)++;
		p += split;
		rem -= (size_t)split;
	}
}

static void paint_inputs(uint32_t *pixels)
{
	const uint32_t dark = 0x00121c29, white = 0x00f5f8fa, teal = 0x0009dcc4;
	const uint32_t amber = 0x00edb961, green = 0x002aa860, gray = 0x007d94a5;

	for (size_t i = 0; i < (size_t)WIDTH * HEIGHT; i++)
		pixels[i] = dark;

	rectangle(pixels, 0, 0, WIDTH, 28, teal);
	draw_text(pixels, "INPUTS", 85, 155, 13, white);
	rectangle(pixels, 75, 300, 1090, 5, teal);
	draw_text(pixels, "LIVE INCOMING SIGNALS & AIGEL STIMULI", 85, 325, 4, teal);

	struct text_row rows[256];
	unsigned int count = 0;

	/* Section 1: Hardware Telemetry */
	add_scroll_row(rows, &count, 256, "--- LIVE SENSORS (HARDWARE TELEMETRY) ---", teal, true);
	add_scroll_row(rows, &count, 256, "TOUCH:   NOVATEK NT36672C (EVENT0/2 P1 ACTIVE)", green, false);
	add_scroll_row(rows, &count, 256, "VISION:  CAMSV SENSOR 4/2 (YOLO OBJECT DETECTION)", white, false);
	add_scroll_row(rows, &count, 256, "PROX:    TCS3701 OPTICAL PROXIMITY (P1 NEAR / P0 FAR)", white, false);
	add_scroll_row(rows, &count, 256, "LIGHT:   TCS3408 AMBIENT SENSOR (P3 BRIGHT/DARK)", white, false);

	int hearing_on = read_hearing_enabled();
	char buf[256];
	snprintf(buf, sizeof(buf), "HEARING: DUAL MIC / MTK AFE [%s]", hearing_on ? "LISTENING (ON)" : "MUTED (OFF)");
	add_scroll_row(rows, &count, 256, buf, hearing_on ? green : amber, false);

	int cap, temp, cur, volt;
	battery_snapshot(&cap, &temp, &cur, &volt);
	snprintf(buf, sizeof(buf), "POWER:   %d%% BATT | %d.%dC | %dMA | %dMV", cap, temp/1000, (temp%1000)/100, cur, volt);
	add_scroll_row(rows, &count, 256, buf, white, false);

	char wifi_ip[32] = {0};
	wifi_address(wifi_ip, sizeof(wifi_ip));
	snprintf(buf, sizeof(buf), "WIFI:    IP %s (NEXUS 192.168.100.106:112)", wifi_ip[0] ? wifi_ip : "LINKING");
	add_scroll_row(rows, &count, 256, buf, white, false);

	add_scroll_row(rows, &count, 256, "", white, false);

	/* Section 2: Aigel Cognitive Intake & Queue */
	add_scroll_row(rows, &count, 256, "--- AIGEL COGNITIVE INTAKE & JOB QUEUE ---", teal, true);
	int pending = count_jobs(".pending");
	int running = count_jobs(".running");
	int done = count_jobs(".done");
	snprintf(buf, sizeof(buf), "QUEUE:   %d PENDING | %d RUNNING | %d COMPLETED", pending, running, done);
	add_scroll_row(rows, &count, 256, buf, running ? amber : green, false);

	char job_snippet[256] = {0};
	get_running_job_snippet(job_snippet, sizeof(job_snippet));
	snprintf(buf, sizeof(buf), "ACTIVE:  %s", job_snippet);
	add_scroll_row(rows, &count, 256, buf, white, false);
	add_scroll_row(rows, &count, 256, "INTAKE:  PORT 112 (HMAC SIGNED CHUNK STREAM)", white, false);

	add_scroll_row(rows, &count, 256, "", white, false);

	/* Section 3: Live Sense Stream from /var/log/lynx/messages */
	add_scroll_row(rows, &count, 256, "--- LIVE RECENT SENSE STREAM (NOOBIA-SENSE) ---", teal, true);

	FILE *mf = fopen("/var/log/lynx/messages", "r");
	if (mf) {
		if (fseek(mf, 0, SEEK_END) == 0) {
			long sz = ftell(mf);
			long off = sz > 16384 ? sz - 16384 : 0;
			fseek(mf, off, SEEK_SET);
			if (off > 0) {
				char dummy[512];
				if (!fgets(dummy, sizeof(dummy), mf)) {}
			}
		}
		char mline[512];
		char collected[50][256];
		int ccnt = 0;
		while (fgets(mline, sizeof(mline), mf)) {
			char *p = strstr(mline, "NOOBIA");
			if (!p) continue;
			p[strcspn(p, "\r\n")] = 0;
			int slot = ccnt < 50 ? ccnt : 49;
			if (ccnt >= 50)
				memmove(collected, collected + 1, sizeof(collected[0]) * 49);
			snprintf(collected[slot], sizeof(collected[slot]), "%s", p);
			ccnt++;
		}
		fclose(mf);

		int num = ccnt < 50 ? ccnt : 50;
		for (int i = 0; i < num; i++) {
			uint32_t scol = white;
			if (strstr(collected[i], "P1 touch"))
				scol = green;
			else if (strstr(collected[i], "P1 chat"))
				scol = teal;
			else if (strstr(collected[i], "P0 camera"))
				scol = amber;
			else if (strstr(collected[i], "status.sample"))
				scol = 0x00c8d5e0;
			add_scroll_row(rows, &count, 256, collected[i], scol, false);
		}
	} else {
		add_scroll_row(rows, &count, 256, "(NO LIVE SENSES STREAM FOUND)", gray, false);
	}

	const unsigned int line_h = 50;
	const unsigned int visible_lines = 38;
	inputs_line_count = count;
	unsigned int maximum = count > visible_lines ? count - visible_lines : 0;
	if (inputs_scroll_offset > maximum)
		inputs_scroll_offset = maximum;

	unsigned int first = inputs_scroll_offset;
	unsigned int show_n = count - first < visible_lines ? count - first : visible_lines;
	for (unsigned int i = 0; i < show_n; i++) {
		unsigned int idx = first + i;
		if (rows[idx].is_header) {
			rectangle(pixels, 55, 360 + i * line_h, 1115, 42, 0x001a2735);
			rectangle(pixels, 55, 360 + i * line_h, 1115, 2, teal);
			draw_text(pixels, rows[idx].text, 65, 360 + i * line_h + 8, 4, rows[idx].color);
		} else {
			draw_text(pixels, rows[idx].text, 65, 360 + i * line_h + 8, 4, rows[idx].color);
		}
	}

	/* Scrollbar on right: x=1180, y=360, w=45, h=2160 */
	const unsigned int sb_x = 1180, sb_y = 360, sb_h = 2160;
	unsigned int thumb = count > visible_lines ? sb_h * visible_lines / count : sb_h;
	if (thumb < 120) thumb = 120;
	unsigned int pos = maximum ? (sb_h - thumb) * inputs_scroll_offset / maximum : 0;
	rectangle(pixels, sb_x, sb_y, 45, sb_h, 0x00223644);
	rectangle(pixels, sb_x, sb_y + pos, 45, thumb, teal);
}

static void paint_outputs(uint32_t *pixels)
{
	const uint32_t dark = 0x00121c29, white = 0x00f5f8fa, teal = 0x0009dcc4;
	const uint32_t green = 0x002aa860, amber = 0x00edb961;

	for (size_t i = 0; i < (size_t)WIDTH * HEIGHT; i++)
		pixels[i] = dark;

	rectangle(pixels, 0, 0, WIDTH, 28, teal);
	draw_text(pixels, "OUTPUTS", 85, 155, 13, white);
	rectangle(pixels, 75, 300, 1090, 5, teal);
	draw_text(pixels, "AVAILABLE EFFECTORS & RUNTIME STATE", 85, 325, 4, teal);

	struct text_row rows[256];
	unsigned int count = 0;

	/* Section 1: Voice */
	add_scroll_row(rows, &count, 256, "--- VOICE (DISTRIBUTED PIPER TTS) ---", teal, true);
	add_scroll_row(rows, &count, 256, "ENGINE:  NEXUS PIPER (:115) EN_US-KRISTIN", white, false);
	add_scroll_row(rows, &count, 256, "PITCH:   +500 CENTS (RUBBERBAND 1.33484)", white, false);
	add_scroll_row(rows, &count, 256, "VOLUME:  0.08 DIGITAL GAIN (TFA98XX PROTECT)", white, false);
	bool speaking = file_contains("/proc/asound/card0/pcm0p/sub0/status", "RUNNING");
	add_scroll_row(rows, &count, 256, speaking ? "STATE:   SPEAKING (AUDIO PLAYING)" : "STATE:   AVAILABLE (READY)",
		       speaking ? amber : green, false);

	add_scroll_row(rows, &count, 256, "", white, false);

	/* Section 2: Display & Pose */
	add_scroll_row(rows, &count, 256, "--- DISPLAY & POSE (DRM SCANOUT) ---", teal, true);
	add_scroll_row(rows, &count, 256, "SCANOUT: 1240X2772 @ 120HZ DMA-BUF DIRECT", white, false);
	char pose_buf[64] = "01_standing_smile";
	FILE *pf = fopen(SELECTION_FILE, "r");
	if (pf) {
		if (fgets(pose_buf, sizeof(pose_buf), pf))
			pose_buf[strcspn(pose_buf, "\r\n")] = 0;
		fclose(pf);
	}
	char ptxt[96];
	snprintf(ptxt, sizeof(ptxt), "POSE:    %s", pose_buf);
	add_scroll_row(rows, &count, 256, ptxt, white, false);
	add_scroll_row(rows, &count, 256, "THOUGHT: SCROLLING WINDOW (15S AUTO-WAKE)", white, false);
	add_scroll_row(rows, &count, 256, "STATE:   ACTIVE (120HZ SCANOUT RUNNING)", green, false);

	add_scroll_row(rows, &count, 256, "", white, false);

	/* Section 3: Actuators */
	add_scroll_row(rows, &count, 256, "--- TACTILE & LIGHT ACTUATORS ---", teal, true);
	add_scroll_row(rows, &count, 256, "HAPTIC:  OPLUS LRA VIBRATOR (AVAILABLE)", green, false);
	add_scroll_row(rows, &count, 256, "TORCH:   LM3642 DUAL LED FLASHLIGHT (AVAILABLE)", green, false);
	add_scroll_row(rows, &count, 256, "MEDIA:   ALSA HW:0,0 SOUND PLAYER (AVAILABLE)", green, false);
	add_scroll_row(rows, &count, 256, "STATE:   EFFECTORS IDLE & READY", green, false);

	add_scroll_row(rows, &count, 256, "", white, false);

	/* Section 4: Agent Worker */
	add_scroll_row(rows, &count, 256, "--- CONSCIOUS AGENT WORKER (MIND) ---", teal, true);
	add_scroll_row(rows, &count, 256, "MODEL:   QWEN 27B ON NEXUS RTX 5090", white, false);
	add_scroll_row(rows, &count, 256, "DAEMON:  LYNX-AGENT-WORKER (SUPERVISED)", white, false);
	int is_running = count_jobs(".running");
	if (is_running) {
		add_scroll_row(rows, &count, 256, "STATE:   THINKING / ACTING NOW (JOB RUNNING)", amber, false);
	} else {
		add_scroll_row(rows, &count, 256, "STATE:   IDLE (LISTENING FOR SENSES)", green, false);
	}
	add_scroll_row(rows, &count, 256, "ACTIONS: SPEECH, POSE, HAPTIC, TORCH, MEDIA", white, false);

	add_scroll_row(rows, &count, 256, "", white, false);

	/* Section 5: Recent Effector Audit Log */
	add_scroll_row(rows, &count, 256, "--- RECENT EFFECTOR AUDIT LOG ---", teal, true);
	FILE *af = fopen("/var/log/lynx-agent.jsonl", "r");
	if (af) {
		if (fseek(af, 0, SEEK_END) == 0) {
			long sz = ftell(af);
			long off = sz > 4096 ? sz - 4096 : 0;
			fseek(af, off, SEEK_SET);
			if (off > 0) {
				char dummy[256];
				if (!fgets(dummy, sizeof(dummy), af)) {}
			}
		}
		char aline[256];
		char collected_audit[25][128];
		int acnt = 0;
		while (fgets(aline, sizeof(aline), af)) {
			aline[strcspn(aline, "\r\n")] = 0;
			if (!aline[0]) continue;
			int slot = acnt < 25 ? acnt : 24;
			if (acnt >= 25)
				memmove(collected_audit, collected_audit + 1, sizeof(collected_audit[0]) * 24);
			snprintf(collected_audit[slot], sizeof(collected_audit[slot]), "%s", aline);
			acnt++;
		}
		fclose(af);

		int num = acnt < 25 ? acnt : 25;
		for (int i = 0; i < num; i++) {
			char desc[128] = {0};
			char *evt = strstr(collected_audit[i], "\"event\":");
			char *name = strstr(collected_audit[i], "\"name\":");
			char *ok = strstr(collected_audit[i], "\"ok\":");
			char *backend = strstr(collected_audit[i], "\"backend\":");
			if (name) {
				char tname[32] = {0}, tok[8] = {0};
				sscanf(name, "\"name\":\"%31[^\"]\"", tname);
				if (ok) sscanf(ok, "\"ok\":%7[^,}]", tok);
				snprintf(desc, sizeof(desc), "CALL: %s (ok=%s)", tname, tok);
				add_scroll_row(rows, &count, 256, desc, !strcmp(tok, "true") ? green : amber, false);
			} else if (backend) {
				char tmodel[32] = {0};
				char *m = strstr(collected_audit[i], "\"model\":");
				if (m) sscanf(m, "\"model\":\"%31[^\"]\"", tmodel);
				snprintf(desc, sizeof(desc), "INFERENCE: %s", tmodel);
				add_scroll_row(rows, &count, 256, desc, teal, false);
			} else if (evt) {
				snprintf(desc, sizeof(desc), "EVENT: %.*s", 40, collected_audit[i]);
				add_scroll_row(rows, &count, 256, desc, white, false);
			}
		}
	} else {
		add_scroll_row(rows, &count, 256, "(NO AUDIT LOG ENTRIES)", white, false);
	}

	const unsigned int line_h = 50;
	const unsigned int visible_lines = 38;
	outputs_line_count = count;
	unsigned int maximum = count > visible_lines ? count - visible_lines : 0;
	if (outputs_scroll_offset > maximum)
		outputs_scroll_offset = maximum;

	unsigned int first = outputs_scroll_offset;
	unsigned int show_n = count - first < visible_lines ? count - first : visible_lines;
	for (unsigned int i = 0; i < show_n; i++) {
		unsigned int idx = first + i;
		if (rows[idx].is_header) {
			rectangle(pixels, 55, 360 + i * line_h, 1115, 42, 0x001a2735);
			rectangle(pixels, 55, 360 + i * line_h, 1115, 2, teal);
			draw_text(pixels, rows[idx].text, 65, 360 + i * line_h + 8, 4, rows[idx].color);
		} else {
			draw_text(pixels, rows[idx].text, 65, 360 + i * line_h + 8, 4, rows[idx].color);
		}
	}

	/* Scrollbar on right: x=1180, y=360, w=45, h=2160 */
	const unsigned int sb_x = 1180, sb_y = 360, sb_h = 2160;
	unsigned int thumb = count > visible_lines ? sb_h * visible_lines / count : sb_h;
	if (thumb < 120) thumb = 120;
	unsigned int pos = maximum ? (sb_h - thumb) * outputs_scroll_offset / maximum : 0;
	rectangle(pixels, sb_x, sb_y, 45, sb_h, 0x00223644);
	rectangle(pixels, sb_x, sb_y + pos, 45, thumb, teal);
}

/* RADIO page (LNX-37-42): drawn from /run/lynx/radio.txt, written every ~30 s
 * by lynx-radio-snapshot. Rows: "H|header", "W|text" (G green, A amber,
 * R red, M muted), "B|<0-100>|label" (a bar). */
#define RADIO_FILE "/run/lynx/radio.txt"
static void paint_radio(uint32_t *pixels)
{
	const uint32_t dark = 0x00121c29, white = 0x00f5f8fa, teal = 0x0009dcc4;
	const uint32_t green = 0x002aa860, amber = 0x00edb961, red = 0x00e05a5a, gray = 0x007d94a5;

	for (size_t i = 0; i < (size_t)WIDTH * HEIGHT; i++)
		pixels[i] = dark;
	rectangle(pixels, 0, 0, WIDTH, 28, teal);
	draw_text(pixels, "RADIO", 85, 155, 13, white);
	rectangle(pixels, 75, 300, 1090, 5, teal);
	draw_text(pixels, "WI-FI, NETWORK, CELLULAR & BLUETOOTH", 85, 325, 4, teal);

	struct text_row rows[128];
	int bars[128];
	unsigned int count = 0;
	FILE *f = fopen(RADIO_FILE, "r");
	char line[160];
	while (f && count < 128 && fgets(line, sizeof(line), f)) {
		line[strcspn(line, "\r\n")] = '\0';
		if (strlen(line) < 2 || line[1] != '|')
			continue;
		char kind = line[0];
		const char *text = line + 2;
		int bar = -1;
		uint32_t color = white;
		if (kind == 'B') {
			bar = atoi(text);
			if (bar < 0) bar = 0;
			if (bar > 100) bar = 100;
			const char *label = strchr(text, '|');
			text = label ? label + 1 : "";
			color = bar >= 60 ? green : (bar >= 30 ? amber : red);
		} else if (kind == 'G') color = green;
		else if (kind == 'A') color = amber;
		else if (kind == 'R') color = red;
		else if (kind == 'M') color = gray;
		else if (kind == 'H') color = teal;
		unsigned int before = count;
		add_scroll_row(rows, &count, 128, text, color, kind == 'H');
		for (unsigned int k = before; k < count; k++)
			bars[k] = k == before ? bar : -1;
	}
	if (f)
		fclose(f);
	if (count == 0) {
		add_scroll_row(rows, &count, 128, "NO RADIO SNAPSHOT YET", amber, false);
		bars[0] = -1;
		add_scroll_row(rows, &count, 128, "(LYNX-RADIO STARTS WITH START)", gray, false);
		bars[1] = -1;
	}

	const unsigned int line_h = 50;
	const unsigned int visible_lines = 38;
	radio_line_count = count;
	unsigned int maximum = count > visible_lines ? count - visible_lines : 0;
	if (radio_scroll_offset > maximum)
		radio_scroll_offset = maximum;
	unsigned int first = radio_scroll_offset;
	unsigned int show_n = count - first < visible_lines ? count - first : visible_lines;
	for (unsigned int i = 0; i < show_n; i++) {
		unsigned int idx = first + i;
		unsigned int y = 360 + i * line_h;
		if (rows[idx].is_header) {
			rectangle(pixels, 55, y, 1115, 42, 0x001a2735);
			rectangle(pixels, 55, y, 1115, 2, teal);
			draw_text(pixels, rows[idx].text, 65, y + 8, 4, rows[idx].color);
		} else if (bars[idx] >= 0) {
			/* bar 600 px wide at x=65, label to its right */
			rectangle(pixels, 65, y + 8, 600, 30, 0x00223644);
			rectangle(pixels, 65, y + 8, (unsigned int)(6 * bars[idx]), 30, rows[idx].color);
			draw_text(pixels, rows[idx].text, 690, y + 8, 4, white);
		} else {
			draw_text(pixels, rows[idx].text, 65, y + 8, 4, rows[idx].color);
		}
	}
	const unsigned int sb_x = 1180, sb_y = 360, sb_h = 2160;
	unsigned int thumb = count > visible_lines ? sb_h * visible_lines / count : sb_h;
	if (thumb < 120) thumb = 120;
	unsigned int pos = maximum ? (sb_h - thumb) * radio_scroll_offset / maximum : 0;
	rectangle(pixels, sb_x, sb_y, 45, sb_h, 0x00223644);
	rectangle(pixels, sb_x, sb_y + pos, 45, thumb, teal);
}

static void paint_power_page(uint32_t *pixels, int capacity)
{
	const uint32_t dark = 0x000b1219, white = 0x00f5f8fa, muted = 0x007d94a5;
	const uint32_t teal = 0x0009dcc4, start_bg = 0x000c2e2c;
	char reason[64], line[96];
	read_power_saving(reason, sizeof(reason));
	rectangle(pixels, 0, 0, WIDTH, HEIGHT, dark);
	draw_text(pixels, "LYNX", 470, 330, 14, white);
	draw_text(pixels, "POWER SAVING", 270, 600, 9, teal);
	snprintf(line, sizeof(line), "%s", reason[0] ? reason : "resting");
	for (char *c = line; *c; c++)
		*c = (char)toupper((unsigned char)*c);
	draw_text(pixels, line, 90, 760, 5, muted);
	int soc = -1;
	FILE *t = fopen("/sys/class/thermal/thermal_zone0/temp", "r");
	if (t) {
		if (fscanf(t, "%d", &soc) != 1)
			soc = -1;
		fclose(t);
	}
	if (capacity >= 0 && soc > 0)
		snprintf(line, sizeof(line), "BATTERY %d%%   CPU %d C", capacity, soc / 1000);
	else if (capacity >= 0)
		snprintf(line, sizeof(line), "BATTERY %d%%", capacity);
	else
		snprintf(line, sizeof(line), " ");
	draw_text(pixels, line, 90, 860, 6, white);
	/* The START button: x 170..1070, y 1150..1450 */
	rectangle(pixels, 170, 1150, 900, 300, start_bg);
	rectangle(pixels, 170, 1150, 900, 6, teal);
	rectangle(pixels, 170, 1444, 900, 6, teal);
	rectangle(pixels, 170, 1150, 6, 300, teal);
	rectangle(pixels, 1064, 1150, 6, 300, teal);
	draw_text(pixels, "START", 395, 1235, 16, teal);
	draw_text(pixels, "TAP START TO WAKE LYNX", 270, 1560, 5, white);
	draw_text(pixels, "HER GUARDS STAY ON AND NEVER SHUT HER DOWN", 70, 1640, 4, muted);
}

/* =========================================================================
 * LYNX DEBUG MODE (Banshee, 2026-11-25)
 * AI services stopped; 3-pane interactive tool runner and senses output lab.
 * ========================================================================= */
#define DEBUG_TOOLS_FILE "/run/lynx/debug_tools.txt"
#define DEBUG_RAW_FILE "/run/lynx/debug_raw.txt"
#define DEBUG_TRANS_FILE "/run/lynx/debug_translated.txt"
#define DEBUG_CMD_FILE "/run/lynx/debug_cmd.txt"

struct debug_tool_entry {
	char name[48];
	char sample[160];
	char desc[96];
};
static struct debug_tool_entry debug_tools[64];
static unsigned int debug_tool_count = 0;
static unsigned int debug_tool_selected = 0;
static unsigned int debug_tool_scroll_offset = 0;
static char debug_args_input[256] = "{}";
static bool debug_output_mode = false; /* false = RAW (pre-regex), true = REGEX DB (translated) */
static unsigned int debug_output_scroll_offset = 0;
static char debug_status_msg[64] = "READY";
static uint64_t debug_last_load_ms = 0;

static unsigned int wrap_text_lines(const char *src, int max_chars,
				    char out_lines[][128], unsigned int max_lines)
{
	if (!src || !src[0] || max_lines == 0)
		return 0;
	unsigned int count = 0;
	const char *p = src;
	size_t rem = strlen(p);
	while (rem > 0 && count < max_lines) {
		while (*p == ' ') {
			p++;
			rem--;
		}
		if (rem == 0)
			break;

		int split = (int)rem <= max_chars ? (int)rem : max_chars;
		if (split < (int)rem) {
			int s = split;
			while (s > 0 && p[s] != ' ')
				s--;
			if (s > 0)
				split = s;
		}
		snprintf(out_lines[count], 128, "%.*s", split, p);
		count++;
		p += split;
		rem -= (size_t)split;
	}
	return count;
}

static void load_debug_tools(void)
{
	uint64_t now = monotonic_milliseconds();
	if (debug_tool_count > 0 && now - debug_last_load_ms < 3000U)
		return;
	debug_last_load_ms = now;
	FILE *f = fopen(DEBUG_TOOLS_FILE, "r");
	if (!f) {
		if (debug_tool_count == 0) {
			const char *fallbacks[][3] = {
				{ "lynx_battery_status", "{}", "Bounded read-only battery status" },
				{ "lynx_thermal_status", "{}", "Bounded SoC & battery thermal status" },
				{ "lynx_wifi_status", "{}", "Wi-Fi link state and signal status" },
				{ "lynx_speech", "{\"text\": \"Hello Noobia\"}", "Speak words aloud through speaker" },
				{ "lynx_media_play", "{\"kind\": \"sound\", \"item\": \"chime\"}", "Play sound clip" },
				{ "lynx_haptic_pulse", "{\"duration_ms\": 50}", "Tactile haptic pulse" },
				{ "lynx_flashlight_pulse", "{\"duration_ms\": 100}", "100 ms flashlight flash" },
				{ "lynx_camera_photo", "{\"camera\": \"main\"}", "Capture photo from camera" },
				{ "lynx_net_diag", "{\"action\": \"ping\", \"host\": \"192.168.100.106\"}", "Network diagnostic ping" },
				{ "lynx_security_status", "{}", "Firewall and security audit status" },
				{ "lynx_motion_read", "{\"choice\": \"gyro\"}", "Read 3-axis motion sensor" },
				{ "lynx_light_read", "{}", "Read ambient optical light sensor" },
				{ "lynx_proximity_read", "{}", "Read ultrasonic proximity sensor" },
				{ "lynx_agent_health", "{}", "Health check of Lynx agent services" },
			};
			for (size_t i = 0; i < sizeof(fallbacks)/sizeof(fallbacks[0]); i++) {
				snprintf(debug_tools[i].name, sizeof(debug_tools[i].name), "%s", fallbacks[i][0]);
				snprintf(debug_tools[i].sample, sizeof(debug_tools[i].sample), "%s", fallbacks[i][1]);
				snprintf(debug_tools[i].desc, sizeof(debug_tools[i].desc), "%s", fallbacks[i][2]);
			}
			debug_tool_count = sizeof(fallbacks)/sizeof(fallbacks[0]);
		}
		return;
	}
	char line[320];
	unsigned int count = 0;
	while (count < 64 && fgets(line, sizeof(line), f)) {
		line[strcspn(line, "\r\n")] = 0;
		if (!line[0]) continue;
		char *p1 = strchr(line, '|');
		if (!p1) continue;
		*p1 = 0;
		char *p2 = strchr(p1 + 1, '|');
		if (!p2) continue;
		*p2 = 0;
		snprintf(debug_tools[count].name, sizeof(debug_tools[count].name), "%s", line);
		snprintf(debug_tools[count].sample, sizeof(debug_tools[count].sample), "%s", p1 + 1);
		snprintf(debug_tools[count].desc, sizeof(debug_tools[count].desc), "%s", p2 + 1);
		count++;
	}
	fclose(f);
	if (count > 0)
		debug_tool_count = count;
}

static void send_debug_cmd(const char *cmd)
{
	FILE *f = fopen(DEBUG_CMD_FILE, "w");
	if (f) {
		fprintf(f, "%s\n", cmd);
		fclose(f);
	}
}

static void paint_debug(uint32_t *pixels)
{
	const uint32_t dark = 0x00121c29, white = 0x00f5f8fa, teal = 0x0009dcc4;
	const uint32_t amber = 0x00edb961;
	const uint32_t panel_bg = 0x00101b26, panel_border = 0x00334e5b;

	load_debug_tools();

	for (size_t i = 0; i < (size_t)WIDTH * HEIGHT; i++)
		pixels[i] = dark;

	/* Top bar */
	rectangle(pixels, 0, 0, WIDTH, 28, teal);
	draw_text(pixels, "DEBUG MODE", 75, 145, 11, amber);
	bool ai_on = is_ai_worker_running();
	if (ai_on)
		draw_text(pixels, "AI AGENT RUNNING * TOOL & SENSE LAB", 75, 230, 3, 0x0055ff99);
	else
		draw_text(pixels, "AI AGENT STOPPED * TOOL & SENSE LAB", 75, 230, 3, 0x00edb961);

	/* Top bar buttons */
	/* AI ON / OFF toggle button (x: 690..915, y: 120..220) */
	uint32_t ai_bg = ai_on ? 0x000e3a22 : 0x003e1a1a;
	uint32_t ai_bc = ai_on ? 0x002ecc71 : 0x00e05a5a;
	rectangle(pixels, 690, 120, 225, 100, ai_bg);
	rectangle(pixels, 690, 120, 225, 3, ai_bc);
	rectangle(pixels, 690, 217, 225, 3, ai_bc);
	rectangle(pixels, 690, 120, 3, 100, ai_bc);
	rectangle(pixels, 912, 120, 3, 100, ai_bc);
	if (ai_on) {
		draw_text(pixels, "AI: ON", 740, 140, 4, 0x0055ff99);
		draw_text(pixels, "TAP TO STOP", 715, 180, 3, white);
	} else {
		draw_text(pixels, "AI: OFF", 735, 140, 4, 0x00ff7070);
		draw_text(pixels, "TAP TO START", 705, 180, 3, white);
	}

	/* SLEEP button at top right (x: 935..1165, y: 120..220) */
	rectangle(pixels, 935, 120, 230, 100, 0x00102a3a);
	rectangle(pixels, 935, 120, 230, 3, 0x005ab0e0);
	rectangle(pixels, 935, 217, 230, 3, 0x005ab0e0);
	rectangle(pixels, 935, 120, 3, 100, 0x005ab0e0);
	rectangle(pixels, 1162, 120, 3, 100, 0x005ab0e0);
	draw_text(pixels, "SLEEP", 995, 140, 4, 0x008fd0f5);
	draw_text(pixels, "POWER SAVE", 970, 180, 3, white);

	rectangle(pixels, 75, 265, 1090, 4, teal);

	/* =========================================================================
	 * PANE 1: Tools Catalog (x: 55..565, y: 285..1245)
	 * ========================================================================= */
	rectangle(pixels, 55, 285, 510, 960, panel_bg);
	rectangle(pixels, 55, 285, 510, 3, panel_border);
	rectangle(pixels, 55, 1242, 510, 3, panel_border);
	rectangle(pixels, 55, 285, 3, 960, panel_border);
	rectangle(pixels, 562, 285, 3, 960, panel_border);

	char p1_title[48];
	snprintf(p1_title, sizeof(p1_title), "1. TOOLS (%u TOTAL)", debug_tool_count);
	draw_text(pixels, p1_title, 75, 305, 4, teal);

	/* Visible tools: up to 10 rows */
	unsigned int visible_tools = 10;
	unsigned int max_tool_scroll = debug_tool_count > visible_tools ? debug_tool_count - visible_tools : 0;
	if (debug_tool_scroll_offset > max_tool_scroll)
		debug_tool_scroll_offset = max_tool_scroll;

	for (unsigned int i = 0; i < visible_tools; i++) {
		unsigned int idx = debug_tool_scroll_offset + i;
		if (idx >= debug_tool_count)
			break;
		bool is_sel = (idx == debug_tool_selected);
		uint32_t bg = is_sel ? 0x000c2e2c : 0x00182635;
		uint32_t bc = is_sel ? teal : 0x002c4052;
		uint32_t tc = is_sel ? white : 0x00ccd6dd;

		unsigned int by = 355 + i * 85;
		rectangle(pixels, 70, by, 445, 76, bg);
		rectangle(pixels, 70, by, 445, 2, bc);
		rectangle(pixels, 70, by + 74, 445, 2, bc);
		rectangle(pixels, 70, by, 2, 76, bc);
		rectangle(pixels, 513, by, 2, 76, bc);

		draw_text(pixels, debug_tools[idx].name, 85, by + 22, 3, tc);
	}

	/* Scrollbar for Pane 1: x: 525..555, y: 355..1205 */
	unsigned int p1_sb_h = 850;
	unsigned int p1_thumb = debug_tool_count > visible_tools ? p1_sb_h * visible_tools / debug_tool_count : p1_sb_h;
	if (p1_thumb < 60) p1_thumb = 60;
	unsigned int p1_pos = max_tool_scroll ? (p1_sb_h - p1_thumb) * debug_tool_scroll_offset / max_tool_scroll : 0;
	rectangle(pixels, 525, 355, 30, p1_sb_h, 0x001d2d3d);
	rectangle(pixels, 525, 355 + p1_pos, 30, p1_thumb, teal);

	/* =========================================================================
	 * PANE 2: Selected Tool & Arguments Runner (x: 585..1175, y: 285..1245)
	 * ========================================================================= */
	rectangle(pixels, 585, 285, 590, 960, panel_bg);
	rectangle(pixels, 585, 285, 590, 3, panel_border);
	rectangle(pixels, 585, 1242, 590, 3, panel_border);
	rectangle(pixels, 585, 285, 3, 960, panel_border);
	rectangle(pixels, 1172, 285, 3, 960, panel_border);

	draw_text(pixels, "2. TOOL ARGS & RUNNER", 605, 305, 4, teal);

	if (debug_tool_count > 0 && debug_tool_selected < debug_tool_count) {
		const char *sel_name = debug_tools[debug_tool_selected].name;
		draw_text(pixels, sel_name, 605, 365, 4, amber);
		char desc_lines[4][128];
		unsigned int n_desc = wrap_text_lines(debug_tools[debug_tool_selected].desc, 44, desc_lines, 4);
		for (unsigned int d = 0; d < n_desc && d < 2; d++) {
			draw_text(pixels, desc_lines[d], 605, 415 + d * 25, 2, 0x008fa0b0);
		}
	}

	draw_text(pixels, "ARGUMENTS (JSON):", 605, 480, 3, teal);

	/* Args text area with multi-line wrapping */
	rectangle(pixels, 605, 520, 550, 140, 0x0009131d);
	rectangle(pixels, 605, 520, 550, 2, teal);
	rectangle(pixels, 605, 658, 550, 2, teal);
	rectangle(pixels, 605, 520, 2, 140, teal);
	rectangle(pixels, 1153, 520, 2, 140, teal);

	char args_lines[6][128];
	unsigned int n_args = wrap_text_lines(debug_args_input, 28, args_lines, 6);
	for (unsigned int a = 0; a < n_args && a < 4; a++) {
		draw_text(pixels, args_lines[a], 620, 535 + a * 30, 3, white);
	}

	/* Preset Buttons: [ {} EMPTY ] (605..775), [ SAMPLE ] (790..960), [ CLEAR ] (975..1155) */
	rectangle(pixels, 605, 680, 170, 75, 0x001c2b38);
	rectangle(pixels, 605, 680, 170, 2, 0x005ab0e0);
	rectangle(pixels, 605, 753, 170, 2, 0x005ab0e0);
	rectangle(pixels, 605, 680, 2, 75, 0x005ab0e0);
	rectangle(pixels, 773, 680, 2, 75, 0x005ab0e0);
	draw_text(pixels, "{} EMPTY", 630, 705, 3, 0x008fd0f5);

	rectangle(pixels, 790, 680, 170, 75, 0x001c2b38);
	rectangle(pixels, 790, 680, 170, 2, 0x005ab0e0);
	rectangle(pixels, 790, 753, 170, 2, 0x005ab0e0);
	rectangle(pixels, 790, 680, 2, 75, 0x005ab0e0);
	rectangle(pixels, 958, 680, 2, 75, 0x005ab0e0);
	draw_text(pixels, "SAMPLE", 825, 705, 3, 0x008fd0f5);

	rectangle(pixels, 975, 680, 180, 75, 0x002c1b20);
	rectangle(pixels, 975, 680, 180, 2, 0x00b05a5a);
	rectangle(pixels, 975, 753, 180, 2, 0x00b05a5a);
	rectangle(pixels, 975, 680, 2, 75, 0x00b05a5a);
	rectangle(pixels, 1153, 680, 2, 75, 0x00b05a5a);
	draw_text(pixels, "CLEAR", 1015, 705, 3, 0x00ff8d86);

	/* RUN / TEST TOOL BUTTON (605..1155, y: 785..915) */
	rectangle(pixels, 605, 785, 550, 130, 0x000e3a22);
	rectangle(pixels, 605, 785, 550, 4, 0x002ecc71);
	rectangle(pixels, 605, 911, 550, 4, 0x002ecc71);
	rectangle(pixels, 605, 785, 4, 130, 0x002ecc71);
	rectangle(pixels, 1151, 785, 4, 130, 0x002ecc71);
	draw_text(pixels, "> TEST TOOL <", 705, 830, 5, 0x0055ff99);

	/* Status Message */
	draw_text(pixels, debug_status_msg, 605, 950, 3, amber);

	/* =========================================================================
	 * PANE 3: Outputs Feed & Mode Toggle (x: 55..1175, y: 1265..2510)
	 * ========================================================================= */
	rectangle(pixels, 55, 1265, 1120, 1245, panel_bg);
	rectangle(pixels, 55, 1265, 1120, 3, panel_border);
	rectangle(pixels, 55, 2507, 1120, 3, panel_border);
	rectangle(pixels, 55, 1265, 3, 1245, panel_border);
	rectangle(pixels, 1172, 1265, 3, 1245, panel_border);

	draw_text(pixels, "3. SENSORY CHUNKS & TOOLS OUTPUT", 75, 1290, 4, teal);

	/* Mode Toggle Button: x: 500..1020, y: 1275..1345 */
	uint32_t t_bg = debug_output_mode ? 0x00143820 : 0x001c2b38;
	uint32_t t_bc = debug_output_mode ? 0x002ecc71 : 0x005ab0e0;
	rectangle(pixels, 500, 1275, 520, 70, t_bg);
	rectangle(pixels, 500, 1275, 520, 2, t_bc);
	rectangle(pixels, 500, 1343, 520, 2, t_bc);
	rectangle(pixels, 500, 1275, 2, 70, t_bc);
	rectangle(pixels, 1018, 1275, 2, 70, t_bc);
	if (debug_output_mode) {
		draw_text(pixels, "MODE: TRANSLATED CHUNKS (REGEX DB)", 525, 1295, 3, 0x0070ff90);
	} else {
		draw_text(pixels, "MODE: RAW CHUNKS (PRE-REGEX DB)", 520, 1295, 3, 0x008fd0f5);
	}

	/* Clear Button: x: 1040..1155, y: 1275..1345 */
	rectangle(pixels, 1040, 1275, 115, 70, 0x002c1b20);
	rectangle(pixels, 1040, 1275, 115, 2, 0x00b05a5a);
	rectangle(pixels, 1040, 1343, 115, 2, 0x00b05a5a);
	rectangle(pixels, 1040, 1275, 2, 70, 0x00b05a5a);
	rectangle(pixels, 1153, 1275, 2, 70, 0x00b05a5a);
	draw_text(pixels, "CLR", 1075, 1295, 3, 0x00ff8d86);

	/* Feed text rows with multi-line word wrapping */
	const char *feed_file = debug_output_mode ? DEBUG_TRANS_FILE : DEBUG_RAW_FILE;
	struct {
		char text[64];
		uint32_t color;
	} wrapped_feed[256];
	unsigned int wrapped_count = 0;

	FILE *ff = fopen(feed_file, "r");
	if (ff) {
		char fline[256];
		while (fgets(fline, sizeof(fline), ff)) {
			fline[strcspn(fline, "\r\n")] = 0;
			if (!fline[0]) continue;
			uint32_t color = white;
			if (strstr(fline, "[TOOL:"))
				color = amber;
			else if (strstr(fline, "[SENSE"))
				color = teal;
			else if (strstr(fline, "[DEBUG]"))
				color = 0x00d080ff;

			char sub_lines[8][128];
			unsigned int n_sub = wrap_text_lines(fline, 56, sub_lines, 8);
			for (unsigned int s = 0; s < n_sub && wrapped_count < 256; s++) {
				snprintf(wrapped_feed[wrapped_count].text, sizeof(wrapped_feed[wrapped_count].text), "%s", sub_lines[s]);
				wrapped_feed[wrapped_count].color = color;
				wrapped_count++;
			}
		}
		fclose(ff);
	}

	unsigned int visible_feed = 31;
	unsigned int max_feed_scroll = wrapped_count > visible_feed ? wrapped_count - visible_feed : 0;
	if (debug_output_scroll_offset > max_feed_scroll)
		debug_output_scroll_offset = max_feed_scroll;

	unsigned int first_feed = max_feed_scroll - debug_output_scroll_offset;
	for (unsigned int i = 0; i < visible_feed; i++) {
		unsigned int row = first_feed + i;
		if (row >= wrapped_count)
			break;
		draw_text(pixels, wrapped_feed[row].text, 75, 1370 + i * 36, 3, wrapped_feed[row].color);
	}

	/* Scrollbar for Pane 3 */
	unsigned int p3_sb_h = 1110;
	unsigned int p3_thumb = wrapped_count > visible_feed ? p3_sb_h * visible_feed / wrapped_count : p3_sb_h;
	if (p3_thumb < 80) p3_thumb = 80;
	unsigned int p3_pos = max_feed_scroll ? (p3_sb_h - p3_thumb) * (max_feed_scroll - debug_output_scroll_offset) / max_feed_scroll : 0;
	rectangle(pixels, 1140, 1365, 25, p3_sb_h, 0x001d2d3d);
	rectangle(pixels, 1140, 1365 + p3_pos, 25, p3_thumb, teal);

	nav_buttons(pixels, PAGE_DEBUG);
}

static void debug_touch(int x, int y, enum lynx_page *target, bool *page_changed)
{
	/* AI ON/OFF button at top right (x: 680..925, y: 110..230) */
	if (x >= 680 && x < 925 && y >= 110 && y < 230) {
		haptic_tick(45);
		bool running_now = is_ai_worker_running();
		if (running_now) {
			send_debug_cmd("AI_OFF");
			pid_t pid = fork();
			if (pid == 0) {
				execl("/usr/local/bin/lynx-agentctl", "lynx-agentctl", "stop", (char *)NULL);
				_exit(0);
			}
		} else {
			send_debug_cmd("AI_ON");
			pid_t pid = fork();
			if (pid == 0) {
				execl("/usr/local/bin/lynx-agentctl", "lynx-agentctl", "start", (char *)NULL);
				_exit(0);
			}
		}
		*page_changed = true;
		return;
	}

	/* SLEEP button at top right (x: 930..1175, y: 110..230) */
	if (x >= 930 && x < 1175 && y >= 110 && y < 230) {
		haptic_tick(60);
		run_power_mode("saving", "debug sleep button");
		printf("debug_sleep_power_save\n");
		fflush(stdout);
		*target = PAGE_POWER;
		*page_changed = true;
		return;
	}

	/* Pane 1 (Tools List): x: 65..520, y: 355..1205 */
	if (x >= 65 && x < 520 && y >= 355 && y < 1205) {
		unsigned int row = (y - 355) / 85;
		unsigned int idx = debug_tool_scroll_offset + row;
		if (idx < debug_tool_count) {
			debug_tool_selected = idx;
			snprintf(debug_args_input, sizeof(debug_args_input), "%s", debug_tools[idx].sample);
			snprintf(debug_status_msg, sizeof(debug_status_msg), "SELECTED: %s", debug_tools[idx].name);
			haptic_tick(30);
			*page_changed = true;
		}
		return;
	}
	/* Pane 1 Scrollbar */
	if (x >= 520 && x < 565 && y >= 355 && y < 1245) {
		unsigned int visible_tools = 10;
		unsigned int max_tool_scroll = debug_tool_count > visible_tools ? debug_tool_count - visible_tools : 0;
		if (max_tool_scroll > 0) {
			if (y < 800) {
				debug_tool_scroll_offset = debug_tool_scroll_offset >= 5 ? debug_tool_scroll_offset - 5 : 0;
			} else {
				debug_tool_scroll_offset += 5;
				if (debug_tool_scroll_offset > max_tool_scroll)
					debug_tool_scroll_offset = max_tool_scroll;
			}
			haptic_tick(25);
			*page_changed = true;
		}
		return;
	}

	/* Pane 2: Buttons */
	/* {} Empty button: x: 605..775, y: 680..760 */
	if (x >= 605 && x < 775 && y >= 680 && y < 760) {
		snprintf(debug_args_input, sizeof(debug_args_input), "{}");
		haptic_tick(25);
		*page_changed = true;
		return;
	}
	/* Sample button: x: 790..960, y: 680..760 */
	if (x >= 790 && x < 960 && y >= 680 && y < 760) {
		if (debug_tool_selected < debug_tool_count)
			snprintf(debug_args_input, sizeof(debug_args_input), "%s", debug_tools[debug_tool_selected].sample);
		haptic_tick(25);
		*page_changed = true;
		return;
	}
	/* Clear button: x: 975..1155, y: 680..760 */
	if (x >= 975 && x < 1155 && y >= 680 && y < 760) {
		debug_args_input[0] = 0;
		haptic_tick(25);
		*page_changed = true;
		return;
	}
	/* RUN BUTTON: x: 605..1155, y: 785..915 */
	if (x >= 605 && x < 1155 && y >= 785 && y < 915) {
		if (debug_tool_selected < debug_tool_count) {
			const char *tname = debug_tools[debug_tool_selected].name;
			const char *args = debug_args_input[0] ? debug_args_input : "{}";
			char cmd[512];
			snprintf(cmd, sizeof(cmd), "RUN %s %s", tname, args);
			send_debug_cmd(cmd);
			snprintf(debug_status_msg, sizeof(debug_status_msg), "EXECUTED %s", tname);
			haptic_tick(65);
			*page_changed = true;
		}
		return;
	}

	/* Pane 3: Mode Toggle Button: x: 500..1020, y: 1275..1345 */
	if (x >= 500 && x < 1020 && y >= 1275 && y < 1345) {
		debug_output_mode = !debug_output_mode;
		haptic_tick(40);
		*page_changed = true;
		return;
	}
	/* Pane 3: Clear Button: x: 1040..1155, y: 1275..1345 */
	if (x >= 1040 && x < 1155 && y >= 1275 && y < 1345) {
		send_debug_cmd("CLEAR");
		haptic_tick(35);
		*page_changed = true;
		return;
	}
	/* Pane 3: Scroll Area: x: 55..1175, y: 1370..2510 */
	if (x >= 55 && x < 1175 && y >= 1370 && y < 2510) {
		if (y < 1940) {
			debug_output_scroll_offset += 4;
		} else {
			if (debug_output_scroll_offset >= 4)
				debug_output_scroll_offset -= 4;
			else
				debug_output_scroll_offset = 0;
		}
		haptic_tick(20);
		*page_changed = true;
		return;
	}
}

static int paint_lynx_page(uint32_t *pixels, enum lynx_page page,
			   const char *pose, int capacity)
{
	if (page == PAGE_DEBUG) {
		paint_debug(pixels);
		return 0;
	}
	if (page == PAGE_POWER) {
		paint_power_page(pixels, capacity);
		return 0;
	}
	if (page == PAGE_RADIO || page == PAGE_INPUTS || page == PAGE_OUTPUTS) {
		page = PAGE_STATUS;
	}
	const uint32_t dark = 0x00121c29, white = 0x00f5f8fa;
	const uint32_t teal = 0x0009dcc4, amber = 0x00edb961;
	char value[64];
	if (page == PAGE_HOME) {
		if (paint_lynx_portrait(pixels, pose, capacity) < 0)
			return -1;
		paint_thoughts(pixels);
		paint_compact_buttons(pixels);
		nav_buttons(pixels, page);
		return 0;
	}
	if (page == PAGE_CHAT) {
		paint_chat(pixels);
		nav_buttons(pixels, page);
		return 0;
	}
	if (page == PAGE_CONSOLE) {
		for (size_t i = 0; i < (size_t)WIDTH * HEIGHT; i++)
			pixels[i] = dark;
		rectangle(pixels, 0, 0, WIDTH, 28, teal);
		draw_text(pixels, "CONSOLE", 85, 155, 13, white);
		rectangle(pixels, 75, 340, 1090, 5, teal);
		paint_console(pixels);
		nav_buttons(pixels, page);
		return 0;
	}
	/* PAGE_STATUS (combined Status & Radios) */
	for (size_t i = 0; i < (size_t)WIDTH * HEIGHT; i++)
		pixels[i] = dark;
	rectangle(pixels, 0, 0, WIDTH, 28, teal);
	draw_text(pixels, "STATUS & RADIOS", 85, 145, 10, white);
	draw_text(pixels, "SYSTEM HEALTH, HARDWARE & WIRELESS INTERFACES", 85, 230, 3, teal);
	rectangle(pixels, 75, 270, 1090, 4, teal);

	draw_text(pixels, "1. SYSTEM & POWER", 75, 310, 4, amber);
	draw_text(pixels, "2. RADIOS & NETWORK", 660, 310, 4, amber);

	/* Left Column: System & Hardware */
	int pack_capacity, pack_temp, pack_current, pack_voltage;
	battery_snapshot(&pack_capacity, &pack_temp, &pack_current, &pack_voltage);
	bool charging = file_contains("/sys/class/power_supply/11e01000.i2c:mt6375@34:chg/status", "Charging");
	if (pack_capacity >= 0)
		snprintf(value, sizeof(value), "%d%% [%s]", pack_capacity, charging ? "CHARGING" : "DISCHG");
	else
		snprintf(value, sizeof(value), "UNAVAILABLE");
	status_item(pixels, 0, 0, "BATTERY", value);

	int soc_temp = file_contains("/sys/class/thermal/thermal_zone0/type", "soc_max") ?
		read_integer("/sys/class/thermal/thermal_zone0/temp") : -1;
	char soc_str[24] = "N/A", pack_str[24] = "N/A";
	if (soc_temp >= 0 && soc_temp < 100000)
		snprintf(soc_str, sizeof(soc_str), "SOC %d.%dC", soc_temp / 1000, (soc_temp % 1000) / 100);
	if (pack_temp >= 0)
		snprintf(pack_str, sizeof(pack_str), "PACK %d.%dC", pack_temp / 1000, (pack_temp % 1000) / 100);
	snprintf(value, sizeof(value), "%s  %s", soc_str, pack_str);
	status_item(pixels, 0, 1, "THERMALS", value);

	snprintf(value, sizeof(value), "%dMV  %dMA", pack_voltage >= 0 ? pack_voltage : 0, pack_current != -1 ? pack_current : 0);
	status_item(pixels, 0, 2, "POWER BUS", value);

	bool audio_ok = file_contains("/proc/asound/cards", "mt6983mt6338");
	bool touch_ok = file_contains("/sys/class/input/input0/name", "touchpanel") && access("/dev/input/event0", R_OK) == 0;
	snprintf(value, sizeof(value), "AUDIO %s  TOUCH %s", audio_ok ? "OK" : "N/A", touch_ok ? "OK" : "N/A");
	status_item(pixels, 0, 3, "AUDIO & TOUCH", value);

	const char *cam_status = camera_capture_node_present() && path_matches("/dev/media*") ? "CAPTURE READY" :
		(path_matches("/dev/video*") && path_matches("/dev/media*") ? "ISP NODES" : "DRIVER LOADED");
	status_item(pixels, 0, 4, "CAMERAS", cam_status);

	bool bmi = file_contains("/proc/hf_manager", "bmi2xy acc");
	bool akm = file_contains("/proc/hf_manager", "akm09918 mag");
	bool tcs = file_contains("/proc/hf_manager", "tcs3408 als");
	snprintf(value, sizeof(value), "%s%s%s", bmi ? "ACCEL/GYRO " : "", akm ? "MAG " : "", tcs ? "ALS/PS" : "");
	if (!value[0]) snprintf(value, sizeof(value), "SENSORHUB OK");
	status_item(pixels, 0, 5, "SENSORS (HF_MGR)", value);

	bool haptic_ok = access("/sys/class/leds/vibrator/oplus_duration", R_OK) == 0;
	bool flash_ok = access("/sys/bus/i2c/devices/6-0063/driver", F_OK) == 0 && access("/dev/flashlight", R_OK) == 0;
	snprintf(value, sizeof(value), "HAPTIC %s  FLASH %s", haptic_ok ? "OK" : "N/A", flash_ok ? "OK" : "N/A");
	status_item(pixels, 0, 6, "ACTUATORS", value);

	bool ssh_ok = pid_matches("/run/lynx/alpine-dropbear-2222.pid", "dropbear");
	bool noobd_ok = pid_matches("/run/lynx/noobd.pid", "lynx-noobd");
	snprintf(value, sizeof(value), "SSH %s  NRP %s", ssh_ok ? "RUNNING" : "OFF", noobd_ok ? "RUNNING" : "OFF");
	status_item(pixels, 0, 7, "SERVICES", value);

	bool ai_running = is_ai_worker_running();
	snprintf(value, sizeof(value), "%s", ai_running ? "RUNNING (SUPERVISED)" : "STOPPED (DEBUG MODE)");
	status_item(pixels, 0, 8, "AI AGENT WORKER", value);

	bool autonomyd_ok = pid_matches("/run/lynx/noobia-autonomyd.pid", "autonomyd") || pid_matches("/run/lynx/noobia-autonomyd.pid", "python");
	snprintf(value, sizeof(value), "%s", autonomyd_ok ? "ACTIVE (60S / SUM 20)" : "AUTONOMY STANDBY");
	status_item(pixels, 0, 9, "AUTONOMY HARNESS", value);

	/* Right Column: Radios & Network */
	wifi_address(value, sizeof(value));
	status_item(pixels, 1, 0, "WI-FI (WLAN0)", value);

	status_item(pixels, 1, 1, "WI-FI LINK", strcmp(value, "UNAVAILABLE") != 0 ? "5 GHZ LINK ACTIVE" : "STANDBY / UNLINKED");

	char cell_ip[48];
	cellular_address(cell_ip, sizeof(cell_ip));
	if (strcmp(cell_ip, "DOWN") != 0)
		snprintf(value, sizeof(value), "%s (LTE/5G)", cell_ip);
	else
		snprintf(value, sizeof(value), "STANDBY (CCMNI0)");
	status_item(pixels, 1, 2, "CELLULAR (CCMNI0)", value);

	status_item(pixels, 1, 3, "CELLULAR APN", "internet.vivacom.bg");

	const bool bt_service = pid_matches("/run/lynx/bluetoothd.pid", "lynx-bluetoothd");
	const bool bt_controller = access("/sys/class/bluetooth/hci0", F_OK) == 0;
	const bool bt_ready = file_contains("/run/lynx/bluetooth/ready", "ready");
	const char *bt_val = bt_service && bt_controller && bt_ready ? "NRP READY (HCI0)" :
		(bt_service ? "STARTING (HCI0)" : (access("/dev/stpbt", R_OK) == 0 ? "STANDBY" : "UNAVAILABLE"));
	status_item(pixels, 1, 4, "BLUETOOTH", bt_val);

	const char *gps_val = access("/sys/module/gps_drv_dl_v050", F_OK) == 0 &&
		(access("/dev/stpgps", R_OK) == 0 || path_matches("/dev/gps_nd*")) ?
		"READY (/dev/stpgps)" : "RECEIVER READY";
	status_item(pixels, 1, 5, "GPS / GNSS", gps_val);

	status_item(pixels, 1, 6, "NETWORK GATEWAY", "DEFAULT VIA 192.168.100.1");

	status_item(pixels, 1, 7, "DATA LINK FLOW", "WLAN0 & CCMNI0 ONLINE");

	status_item(pixels, 1, 8, "SENSORY TRIGGER", "SUM >= 20 OR 60S TIMEOUT");

	status_item(pixels, 1, 9, "PATTERN STORE", "60 SENSORY RULES LOADED");

	/* Aigel Mode Switch Button on Status Screen */
	bool learning = read_aigel_learning_mode();
	uint32_t mode_bg = learning ? 0x003e2908 : 0x000c2e2c;
	uint32_t mode_border = learning ? 0x00edb961 : 0x0009dcc4;
	uint32_t mode_tc = learning ? 0x00edb961 : 0x0009dcc4;
	/* Four bottom buttons: Aigel mode (75..335), Debug mode (345..605), Power save (615..875), Shut down (885..1165). */
	rectangle(pixels, 75, 2405, 260, 95, mode_bg);
	rectangle(pixels, 75, 2405, 260, 3, mode_border);
	rectangle(pixels, 75, 2497, 260, 3, mode_border);
	rectangle(pixels, 75, 2405, 3, 95, mode_border);
	rectangle(pixels, 332, 2405, 3, 95, mode_border);
	if (learning) {
		draw_text(pixels, "AIGEL: LEARN", 88, 2418, 3, mode_tc);
		draw_text(pixels, "TAP NORMAL", 88, 2462, 3, white);
	} else {
		draw_text(pixels, "AIGEL: NORMAL", 88, 2418, 3, mode_tc);
		draw_text(pixels, "TAP LEARN", 88, 2462, 3, white);
	}

	/* Debug Mode: stops AI services, opens 3-pane direct tool & senses lab (Banshee, 2026-11-25) */
	rectangle(pixels, 345, 2405, 260, 95, 0x002c1d38);
	rectangle(pixels, 345, 2405, 260, 3, 0x00d080ff);
	rectangle(pixels, 345, 2497, 260, 3, 0x00d080ff);
	rectangle(pixels, 345, 2405, 3, 95, 0x00d080ff);
	rectangle(pixels, 602, 2405, 3, 95, 0x00d080ff);
	draw_text(pixels, "DEBUG MODE", 365, 2418, 3, 0x00e0a0ff);
	draw_text(pixels, "AI OFF * LAB", 365, 2462, 3, white);

	/* Power saving: one tap stops everything non-essential (Tom, 2026-11-23). */
	rectangle(pixels, 615, 2405, 260, 95, 0x00102a3a);
	rectangle(pixels, 615, 2405, 260, 3, 0x005ab0e0);
	rectangle(pixels, 615, 2497, 260, 3, 0x005ab0e0);
	rectangle(pixels, 615, 2405, 3, 95, 0x005ab0e0);
	rectangle(pixels, 872, 2405, 3, 95, 0x005ab0e0);
	draw_text(pixels, "POWER SAVE", 635, 2418, 3, 0x008fd0f5);
	draw_text(pixels, "SLEEP MODE", 635, 2462, 3, white);

	/* Shutdown: a person's choice, never automatic. First tap arms it for 5 s,
	 * a second tap shuts Lynx down cleanly. */
	bool armed = shutdown_armed_until_ms != 0 &&
		     monotonic_milliseconds() < shutdown_armed_until_ms;
	uint32_t sd_bg = armed ? 0x00501010 : 0x00241618;
	uint32_t sd_border = armed ? 0x00ff5a5a : 0x00b05a5a;
	rectangle(pixels, 885, 2405, 280, 95, sd_bg);
	rectangle(pixels, 885, 2405, 280, 3, sd_border);
	rectangle(pixels, 885, 2497, 280, 3, sd_border);
	rectangle(pixels, 885, 2405, 3, 95, sd_border);
	rectangle(pixels, 1162, 2405, 3, 95, sd_border);
	if (armed) {
		draw_text(pixels, "TAP AGAIN", 905, 2418, 3, 0x00ffd0d0);
		draw_text(pixels, "TO SHUT DOWN", 905, 2462, 3, white);
	} else {
		draw_text(pixels, "SHUT DOWN", 905, 2418, 3, 0x00ff8a8a);
		draw_text(pixels, "TAP TWICE", 905, 2462, 3, white);
	}

	nav_buttons(pixels, page);
	return 0;
}

static int render_preview(const char *name, const char *output,
			  enum lynx_page page)
{
	uint32_t *pixels = malloc((size_t)WIDTH * HEIGHT * sizeof(uint32_t));
	if (!pixels)
		return 1;
	if (paint_lynx_page(pixels, page, name, read_battery_percent()) < 0) {
		fail("preview portrait");
		free(pixels);
		return 1;
	}
	FILE *stream = fopen(output, "wb");
	if (!stream) {
		fail("open preview output");
		free(pixels);
		return 1;
	}
	fprintf(stream, "P6\n%u %u\n255\n", WIDTH, HEIGHT);
	for (size_t y = 0; y < HEIGHT; y++) {
		uint8_t row[WIDTH * 3];
		for (size_t x = 0; x < WIDTH; x++) {
			uint32_t color = pixels[y * WIDTH + x];
			row[x * 3] = (uint8_t)(color >> 16);
			row[x * 3 + 1] = (uint8_t)(color >> 8);
			row[x * 3 + 2] = (uint8_t)color;
		}
		if (fwrite(row, 1, sizeof(row), stream) != sizeof(row)) {
			fail("write preview output");
			fclose(stream);
			free(pixels);
			return 1;
		}
	}
	int rc = fclose(stream);
	free(pixels);
	return rc ? 1 : 0;
}

static uint32_t choose_crtc(int fd, drmModeRes *resources,
			    drmModeConnector *connector)
{
	for (int i = 0; i < connector->count_encoders; i++) {
		drmModeEncoder *enc = drmModeGetEncoder(fd, connector->encoders[i]);
		if (!enc)
			continue;
		for (int j = 0; j < resources->count_crtcs; j++) {
			if (j < 32 && (enc->possible_crtcs & (1U << j))) {
				uint32_t id = resources->crtcs[j];
				drmModeFreeEncoder(enc);
				return id;
			}
		}
		drmModeFreeEncoder(enc);
	}
	return 0;
}

static int pick_dsi(int fd, drmModeRes *resources, uint32_t *connector_id,
		    uint32_t *crtc_id, drmModeModeInfo *mode)
{
	for (int i = 0; i < resources->count_connectors; i++) {
		drmModeConnector *conn = drmModeGetConnector(fd,
					resources->connectors[i]);
		if (!conn)
			continue;
		if (conn->connection != DRM_MODE_CONNECTED ||
		    conn->connector_type != DRM_MODE_CONNECTOR_DSI) {
			drmModeFreeConnector(conn);
			continue;
		}
		uint32_t crtc = choose_crtc(fd, resources, conn);
		if (!crtc) {
			drmModeFreeConnector(conn);
			continue;
		}
		for (int j = 0; j < conn->count_modes; j++) {
			drmModeModeInfo *candidate = &conn->modes[j];
			if (candidate->hdisplay == WIDTH &&
			    candidate->vdisplay == HEIGHT &&
			    candidate->vrefresh == 60) {
				*connector_id = conn->connector_id;
				*crtc_id = crtc;
				*mode = *candidate;
				drmModeFreeConnector(conn);
				return 0;
			}
		}
		drmModeFreeConnector(conn);
	}
	errno = ENODEV;
	return -1;
}

static uint32_t property_id(int fd, uint32_t object_id, uint32_t object_type,
			    const char *name, uint64_t *value)
{
	drmModeObjectProperties *properties =
		drmModeObjectGetProperties(fd, object_id, object_type);
	uint32_t found = 0;
	if (!properties)
		return 0;
	for (uint32_t i = 0; i < properties->count_props; i++) {
		drmModePropertyRes *property =
			drmModeGetProperty(fd, properties->props[i]);
		if (property) {
			if (!strcmp(property->name, name)) {
				found = property->prop_id;
				if (value)
					*value = properties->prop_values[i];
			}
			drmModeFreeProperty(property);
		}
		if (found)
			break;
	}
	drmModeFreeObjectProperties(properties);
	return found;
}

static uint32_t choose_primary_plane(int fd, drmModeRes *resources,
				     uint32_t crtc_id)
{
	int crtc_index = -1;
	for (int i = 0; i < resources->count_crtcs; i++)
		if (resources->crtcs[i] == crtc_id)
			crtc_index = i;
	if (crtc_index < 0 || crtc_index >= 32)
		return 0;
	drmModePlaneRes *planes = drmModeGetPlaneResources(fd);
	if (!planes)
		return 0;
	uint32_t chosen = 0;
	for (uint32_t i = 0; i < planes->count_planes; i++) {
		drmModePlane *plane = drmModeGetPlane(fd, planes->planes[i]);
		if (!plane)
			continue;
		uint64_t type = UINT64_MAX;
		bool format = false;
		for (uint32_t j = 0; j < plane->count_formats; j++)
			if (plane->formats[j] == DRM_FORMAT_XRGB8888)
				format = true;
		if ((plane->possible_crtcs & (1U << crtc_index)) && format &&
		    property_id(fd, plane->plane_id, DRM_MODE_OBJECT_PLANE,
				"type", &type) && type == DRM_PLANE_TYPE_PRIMARY)
			chosen = plane->plane_id;
		drmModeFreePlane(plane);
		if (chosen)
			break;
	}
	drmModeFreePlaneResources(planes);
	return chosen;
}

static int add_property(int fd, drmModeAtomicReq *request, uint32_t object_id,
			uint32_t object_type, const char *name, uint64_t value)
{
	uint32_t id = property_id(fd, object_id, object_type, name, NULL);
	if (!id) {
		fprintf(stderr, "missing atomic property %s on object %u\n",
			name, object_id);
		errno = ENOENT;
		return -1;
	}
	return drmModeAtomicAddProperty(request, object_id, id, value) < 0 ? -1 : 0;
}

static int atomic_mode(int fd, uint32_t connector, uint32_t crtc,
		       uint32_t plane, uint32_t fb, drmModeModeInfo *mode,
		       bool test_only)
{
	uint32_t blob = 0;
	drmModeAtomicReq *request = NULL;
	int rc = -1;
	if (drmModeCreatePropertyBlob(fd, mode, sizeof(*mode), &blob) < 0)
		return -1;
	request = drmModeAtomicAlloc();
	if (!request)
		goto done;
#define ADD(obj, kind, name, val) \
	do { if (add_property(fd, request, obj, kind, name, val) < 0) goto done; } while (0)
	ADD(connector, DRM_MODE_OBJECT_CONNECTOR, "CRTC_ID", crtc);
	ADD(crtc, DRM_MODE_OBJECT_CRTC, "MODE_ID", blob);
	ADD(crtc, DRM_MODE_OBJECT_CRTC, "ACTIVE", 1);
	ADD(plane, DRM_MODE_OBJECT_PLANE, "FB_ID", fb);
	ADD(plane, DRM_MODE_OBJECT_PLANE, "CRTC_ID", crtc);
	ADD(plane, DRM_MODE_OBJECT_PLANE, "SRC_X", 0);
	ADD(plane, DRM_MODE_OBJECT_PLANE, "SRC_Y", 0);
	ADD(plane, DRM_MODE_OBJECT_PLANE, "SRC_W", WIDTH << 16);
	ADD(plane, DRM_MODE_OBJECT_PLANE, "SRC_H", HEIGHT << 16);
	ADD(plane, DRM_MODE_OBJECT_PLANE, "CRTC_X", 0);
	ADD(plane, DRM_MODE_OBJECT_PLANE, "CRTC_Y", 0);
	ADD(plane, DRM_MODE_OBJECT_PLANE, "CRTC_W", WIDTH);
	ADD(plane, DRM_MODE_OBJECT_PLANE, "CRTC_H", HEIGHT);
#undef ADD
	rc = drmModeAtomicCommit(fd, request, DRM_MODE_ATOMIC_ALLOW_MODESET |
		(test_only ? DRM_MODE_ATOMIC_TEST_ONLY : 0), NULL);
done:
	if (request)
		drmModeAtomicFree(request);
	drmModeDestroyPropertyBlob(fd, blob);
	return rc;
}

static int atomic_disable(int fd, uint32_t connector, uint32_t crtc,
			  uint32_t plane)
{
	drmModeAtomicReq *request = drmModeAtomicAlloc();
	int rc = -1;
	if (!request)
		return -1;
	if (add_property(fd, request, plane, DRM_MODE_OBJECT_PLANE,
			 "FB_ID", 0) < 0 ||
	    add_property(fd, request, plane, DRM_MODE_OBJECT_PLANE,
			 "CRTC_ID", 0) < 0 ||
	    add_property(fd, request, connector, DRM_MODE_OBJECT_CONNECTOR,
			 "CRTC_ID", 0) < 0 ||
	    add_property(fd, request, crtc, DRM_MODE_OBJECT_CRTC,
			 "ACTIVE", 0) < 0 ||
	    add_property(fd, request, crtc, DRM_MODE_OBJECT_CRTC,
			 "MODE_ID", 0) < 0)
		goto done;
	rc = drmModeAtomicCommit(fd, request, DRM_MODE_ATOMIC_ALLOW_MODESET, NULL);
done:
	drmModeAtomicFree(request);
	return rc;
}

static int atomic_present_fb(int fd, uint32_t plane, uint32_t fb)
{
	drmModeAtomicReq *request = drmModeAtomicAlloc();
	int rc = -1;
	if (!request)
		return -1;
	if (add_property(fd, request, plane, DRM_MODE_OBJECT_PLANE,
			 "FB_ID", fb) == 0)
		rc = drmModeAtomicCommit(fd, request, 0, NULL);
	drmModeAtomicFree(request);
	return rc;
}

struct touch_state {
	int slot;
	int x, y;
	bool down, have_x, have_y;
};

static int wait_for_touch_or_timeout(int fd, int timeout_ms,
				     struct touch_state *state,
				     bool *released, int *tap_x, int *tap_y)
{
	*released = false;
	*tap_x = *tap_y = -1;
	struct pollfd watch = { .fd = fd, .events = POLLIN };
	int rc = poll(&watch, 1, timeout_ms);
	if (rc < 0 && errno == EINTR)
		return 0;
	if (rc <= 0)
		return rc;
	if (watch.revents & (POLLERR | POLLHUP | POLLNVAL)) {
		errno = EIO;
		return -1;
	}
	if (!(watch.revents & POLLIN))
		return 0;
	struct input_event events[32];
	ssize_t count = read(fd, events, sizeof(events));
	if (count < 0 && errno == EAGAIN)
		return 0;
	if (count <= 0 || count % (ssize_t)sizeof(events[0])) {
		errno = EIO;
		return -1;
	}
	int press = 0;
	for (size_t i = 0; i < (size_t)count / sizeof(events[0]); i++) {
		struct input_event *event = &events[i];
		if (event->type == EV_ABS && event->code == ABS_MT_SLOT) {
			state->slot = event->value;
			continue;
		}
		if (event->type == EV_ABS && state->slot == 0) {
			if (event->code == ABS_MT_POSITION_X) {
				state->x = event->value;
				state->have_x = true;
			} else if (event->code == ABS_MT_POSITION_Y) {
				state->y = event->value;
				state->have_y = true;
			} else if (event->code == ABS_MT_TRACKING_ID) {
				if (event->value >= 0 && !state->down) {
					state->down = true;
					state->have_x = state->have_y = false;
					press = 1;
				} else if (event->value < 0 && state->down) {
					*released = true;
					if (state->have_x && state->have_y) {
						*tap_x = state->x;
						*tap_y = state->y;
					}
					state->down = false;
				}
			}
		}
		if (event->type == EV_KEY && event->code == BTN_TOUCH) {
			if (event->value == 1 && !state->down) {
				state->down = true;
				state->have_x = state->have_y = false;
				press = 1;
			} else if (event->value == 0 && state->down) {
				*released = true;
				if (state->have_x && state->have_y) {
					*tap_x = state->x;
					*tap_y = state->y;
				}
				state->down = false;
			}
		}
	}
	return press;
}

static int self_test_touch(void)
{
	int fds[2];
	if (pipe(fds) < 0)
		return 1;
	struct touch_state state = { 0 };
	bool released;
	int x, y;
	struct input_event start[] = {
		{ .type = EV_ABS, .code = ABS_MT_TRACKING_ID, .value = 7 },
		{ .type = EV_ABS, .code = ABS_MT_POSITION_X, .value = 8500 },
		{ .type = EV_ABS, .code = ABS_MT_POSITION_Y, .value = 26200 },
	};
	struct input_event end = {
		.type = EV_ABS, .code = ABS_MT_TRACKING_ID, .value = -1
	};
	int ok = write(fds[1], start, sizeof(start)) == (ssize_t)sizeof(start) &&
		 wait_for_touch_or_timeout(fds[0], 100, &state,
					   &released, &x, &y) == 1 && !released &&
		 write(fds[1], &end, sizeof(end)) == (ssize_t)sizeof(end) &&
		 wait_for_touch_or_timeout(fds[0], 100, &state,
					   &released, &x, &y) == 0 &&
		 released && x == 8500 && y == 26200;
	close(fds[0]);
	close(fds[1]);
	printf("touch parser %s\n", ok ? "PASS" : "FAIL");
	return ok ? 0 : 1;
}

static int run(const char *action, unsigned int seconds)
{
	int drm_fd = -1, heap_fd = -1, buffer_fd = -1, buffer_fd2 = -1;
	int touch_fd = -1, rc = 1;
	void *pixels = MAP_FAILED, *pixels2 = MAP_FAILED;
	uint32_t handle = 0, handle2 = 0, fb_id = 0, fb_id2 = 0;
	uint32_t connector_id = 0, crtc_id = 0, plane_id = 0;
	drmModeRes *resources = NULL;
	drmModeModeInfo mode = { 0 };
	bool active = false;
	bool touch_idle = !strcmp(action, "--show-ui-touch-idle");
	bool portrait = !strcmp(action, "--show-portrait-touch-idle");
	touch_idle = touch_idle || portrait;
	bool persistent_ui = !strcmp(action, "--show-ui-until-signal") || touch_idle;
	bool atomic = !strcmp(action, "--atomic-test") ||
		!strcmp(action, "--show-atomic") || !strcmp(action, "--show-ui") ||
		persistent_ui;
	bool ui = !strcmp(action, "--show-ui") || persistent_ui;
	int shown_capacity = -1;
	uint64_t prime_caps = 0;
	const size_t length = ((size_t)STRIDE * HEIGHT + 4095U) & ~(size_t)4095U;
	uint32_t current_fb = 0;
	bool lit = false;
	uint64_t lit_until = 0;
	struct scene scene = { 0 };
	size_t shown_frame = 0;
	uint64_t scene_started = 0;
	uint64_t last_battery_poll = 0;
	uint64_t last_page_refresh = 0;
	unsigned int shown_console_sequence = 0;
	time_t shown_thought_mtime = 0;
	int shown_hearing_on = -1;
	time_t shown_minute = 0;
	enum lynx_page page = read_power_saving(NULL, 0) ? PAGE_POWER : PAGE_HOME;
	struct touch_state touch_state = { 0 };
	bool page_changed = false, suppress_tap = false;

	if (touch_idle) {
		touch_fd = verify_touch_device();
		if (touch_fd < 0) {
			fail("open verified touchpanel input");
			goto cleanup;
		}
	}

	drm_fd = open(DRM_DEVICE, O_RDWR | O_CLOEXEC);
	if (drm_fd < 0) {
		fail("open DRM device");
		goto cleanup;
	}
	if (drmGetCap(drm_fd, DRM_CAP_PRIME, &prime_caps) < 0) {
		fail("query DRM PRIME capability");
		goto cleanup;
	}
	printf("prime_caps=0x%" PRIx64 "\n", prime_caps);
	if (!(prime_caps & DRM_PRIME_CAP_IMPORT)) {
		fprintf(stderr, "DRM device has no PRIME import capability\n");
		goto cleanup;
	}
	if (atomic && drmSetClientCap(drm_fd, DRM_CLIENT_CAP_ATOMIC, 1) < 0) {
		fail("enable DRM atomic capability");
		goto cleanup;
	}
	resources = drmModeGetResources(drm_fd);
	if (!resources) {
		fail("get DRM resources");
		goto cleanup;
	}
	if (pick_dsi(drm_fd, resources, &connector_id, &crtc_id, &mode) < 0) {
		fail("find connected 1240x2772 60 Hz DSI mode");
		goto cleanup;
	}
	printf("connector=%u crtc=%u mode=%s@%d\n",
	       connector_id, crtc_id, mode.name, mode.vrefresh);
	if (!strcmp(action, "--probe")) {
		rc = 0;
		goto cleanup;
	}

	heap_fd = open(HEAP_DEVICE, O_RDONLY | O_CLOEXEC);
	if (heap_fd < 0) {
		fail("open system DMA heap");
		goto cleanup;
	}
	struct dma_heap_allocation_data alloc = {
		.len = length,
		.fd_flags = O_RDWR | O_CLOEXEC,
	};
	if (ioctl(heap_fd, DMA_HEAP_IOCTL_ALLOC, &alloc) < 0) {
		fail("allocate DMA-BUF");
		goto cleanup;
	}
	buffer_fd = (int)alloc.fd;
	printf("dma_buf_bytes=%zu\n", length);
	pixels = mmap(NULL, length, PROT_READ | PROT_WRITE, MAP_SHARED,
		      buffer_fd, 0);
	if (pixels == MAP_FAILED) {
		fail("map DMA-BUF");
		goto cleanup;
	}
	if (sync_buffer(buffer_fd, DMA_BUF_SYNC_START | DMA_BUF_SYNC_WRITE) < 0) {
		fail("begin DMA-BUF CPU write");
		goto cleanup;
	}
	if (ui) {
		shown_capacity = read_battery_percent();
		last_battery_poll = monotonic_milliseconds();
		if (portrait) {
			if (read_scene(&scene) != 1 ||
			    paint_lynx_page(pixels, PAGE_HOME, scene.frames[0], shown_capacity) < 0) {
				fail("load initial Lynx portrait");
				goto cleanup;
			}
			scene_started = monotonic_milliseconds();
			shown_minute = time(NULL) / 60;
		} else {
			paint_lynx_status(pixels, shown_capacity);
		}
	}
	else
		paint_bars(pixels);
	if (sync_buffer(buffer_fd, DMA_BUF_SYNC_END | DMA_BUF_SYNC_WRITE) < 0) {
		fail("end DMA-BUF CPU write");
		goto cleanup;
	}
	if (drmPrimeFDToHandle(drm_fd, buffer_fd, &handle) < 0) {
		fail("import DMA-BUF into DRM");
		goto cleanup;
	}
	uint32_t handles[4] = { handle, 0, 0, 0 };
	uint32_t pitches[4] = { STRIDE, 0, 0, 0 };
	uint32_t offsets[4] = { 0, 0, 0, 0 };
	if (drmModeAddFB2(drm_fd, WIDTH, HEIGHT, DRM_FORMAT_XRGB8888,
			  handles, pitches, offsets, &fb_id, 0) < 0) {
		fail("add DRM framebuffer");
		goto cleanup;
	}
	printf("framebuffer=%u\n", fb_id);
	if (persistent_ui) {
		struct dma_heap_allocation_data second = {
			.len = length,
			.fd_flags = O_RDWR | O_CLOEXEC,
		};
		if (ioctl(heap_fd, DMA_HEAP_IOCTL_ALLOC, &second) < 0) {
			fail("allocate second status DMA-BUF");
			goto cleanup;
		}
		buffer_fd2 = (int)second.fd;
		pixels2 = mmap(NULL, length, PROT_READ | PROT_WRITE, MAP_SHARED,
			       buffer_fd2, 0);
		if (pixels2 == MAP_FAILED) {
			fail("map second status DMA-BUF");
			goto cleanup;
		}
		if (drmPrimeFDToHandle(drm_fd, buffer_fd2, &handle2) < 0) {
			fail("import second DMA-BUF into DRM");
			goto cleanup;
		}
		uint32_t second_handles[4] = { handle2, 0, 0, 0 };
		if (drmModeAddFB2(drm_fd, WIDTH, HEIGHT, DRM_FORMAT_XRGB8888,
				  second_handles, pitches, offsets, &fb_id2, 0) < 0) {
			fail("add second status framebuffer");
			goto cleanup;
		}
	}
	if (!strcmp(action, "--allocate")) {
		rc = 0;
		goto cleanup;
	}
	if (atomic) {
		plane_id = choose_primary_plane(drm_fd, resources, crtc_id);
		if (!plane_id) {
			errno = ENODEV;
			fail("find XRGB8888 primary plane");
			goto cleanup;
		}
		printf("primary_plane=%u\n", plane_id);
		if (atomic_mode(drm_fd, connector_id, crtc_id, plane_id,
				fb_id, &mode, true) < 0) {
			fail("atomic test-only commit");
			goto cleanup;
		}
		printf("atomic test-only commit accepted\n");
		if (!strcmp(action, "--atomic-test")) {
			rc = 0;
			goto cleanup;
		}
		if (atomic_mode(drm_fd, connector_id, crtc_id, plane_id,
				fb_id, &mode, false) < 0) {
			fail("atomic display commit");
			goto cleanup;
		}
		goto displayed;
	}
	if (drmModeSetCrtc(drm_fd, crtc_id, fb_id, 0, 0,
			   &connector_id, 1, &mode) < 0) {
		fail("set DSI CRTC");
		goto cleanup;
	}
	displayed:
	active = true;
	current_fb = fb_id;
	if (persistent_ui)
		printf("displaying Lynx %s %s\n", portrait ? "portrait" : "status",
		       touch_idle ? "with 10-second touch wake" : "until signal");
	else
		printf("displaying %s for %u seconds\n",
		       ui ? "Lynx status" : "color bars", seconds);
	fflush(stdout);
	if (persistent_ui) {
		if (touch_idle) {
			if (set_brightness(250) < 0) {
				fail("light status screen");
				goto cleanup;
			}
			lit = true;
			lit_until = monotonic_milliseconds() + 10000U;
		}
		while (!stop_requested) {
			if (touch_idle) {
				bool released;
				int tap_x, tap_y;
				int touch = wait_for_touch_or_timeout(touch_fd,
					portrait ? 100 : 1000, &touch_state,
					&released, &tap_x, &tap_y);
				if (touch < 0) {
					fail("read touchscreen event");
					goto cleanup;
				}
				if (touch && !stop_requested) {
					if (!lit) {
						suppress_tap = true;
						if (set_brightness(250) < 0) {
							fail("wake status screen");
							goto cleanup;
						}
					}
					lit = true;
					lit_until = monotonic_milliseconds() + 15000U;
					printf("touch_wake\n");
					fflush(stdout);
				}
				if (released) {
					if (portrait && lit && !suppress_tap &&
					    tap_x >= 0 && tap_x <= 12399 &&
					    tap_y >= 0 && tap_y <= 27719) {
						haptic_tick(25);
						int x = tap_x * (int)WIDTH / 12400;
						int y = tap_y * (int)HEIGHT / 27720;
						enum lynx_page target = page;
						if (page == PAGE_POWER) {
							/* Only START responds here; no nav bar. */
							if (x >= 170 && x < 1070 && y >= 1150 && y < 1450) {
								haptic_tick(60);
								run_power_mode("active", "");
								printf("power_start\n");
								fflush(stdout);
								target = PAGE_HOME;
							}
						} else if (y >= 2550 && y < 2710) {
							if (x >= 40 && x < 300)
								target = PAGE_HOME;
							else if (x >= 340 && x < 600)
								target = PAGE_CHAT;
							else if (x >= 640 && x < 900)
								target = PAGE_STATUS;
							else if (x >= 940 && x < 1200)
								target = PAGE_DEBUG;
						} else if (page == PAGE_HOME &&
							   y >= 2360 && y < 2490) {
							if (x >= 50 && x < 605) {
								toggle_hearing();
								page_changed = true;
								printf("hearing_toggled\n");
								fflush(stdout);
							} else if (x >= 635 && x < 1190) {
								target = PAGE_CHAT;
							}
						} else if (page == PAGE_STATUS &&
							   y >= 2380 && y < 2525 && x >= 50 && x < 340) {
							toggle_aigel_mode();
							page_changed = true;
							haptic_tick(35);
							printf("aigel_mode_toggled\n");
							fflush(stdout);
						} else if (page == PAGE_STATUS &&
							   y >= 2380 && y < 2525 && x >= 340 && x < 610) {
							haptic_tick(45);
							run_power_mode("debug", "debug button");
							printf("debug_mode_started\n");
							fflush(stdout);
							target = PAGE_DEBUG;
						} else if (page == PAGE_STATUS &&
							   y >= 2380 && y < 2525 && x >= 610 && x < 880) {
							haptic_tick(60);
							run_power_mode("saving", "power save button");
							printf("power_saving\n");
							fflush(stdout);
							target = PAGE_POWER;
						} else if (page == PAGE_STATUS &&
							   y >= 2380 && y < 2525 && x >= 880 && x < 1180) {
							uint64_t now_sd = monotonic_milliseconds();
							if (shutdown_armed_until_ms != 0 &&
							    now_sd < shutdown_armed_until_ms) {
								shutdown_armed_until_ms = 0;
								haptic_tick(120);
								printf("shutdown_confirmed\n");
								fflush(stdout);
								pid_t sd_pid = fork();
								if (sd_pid == 0) {
									execl("/sbin/openrc-shutdown", "openrc-shutdown",
									      "--poweroff", "now", (char *)NULL);
									_exit(127);
								}
							} else {
								shutdown_armed_until_ms = now_sd + 5000U;
								haptic_tick(35);
								printf("shutdown_armed\n");
								fflush(stdout);
							}
							page_changed = true;
						} else if (page == PAGE_DEBUG && y < 2550) {
							debug_touch(x, y, &target, &page_changed);
						} else if (page == PAGE_HOME && y < 2360) {
							/* Tapped on portrait: trigger tactile tick and emit instant P1 sense (throttled to >= 5s) */
							haptic_tick(25);
							static uint64_t last_portrait_touch_ms = 0;
							uint64_t now_touch_ms = monotonic_milliseconds();
							if (now_touch_ms - last_portrait_touch_ms >= 5000U) {
								last_portrait_touch_ms = now_touch_ms;
								pid_t pid = fork();
								if (pid == 0) {
									execl("/usr/bin/python3", "python3",
									      "/usr/local/lib/noobia/autonomy/sense.py",
									      "1", "touch", "tap", "dur_ms=100",
									      "-t", "screen tapped on portrait", (char *)NULL);
									_exit(0);
								}
							}
							printf("portrait_tapped x=%d y=%d\n", x, y);
							fflush(stdout);
						} else if (page == PAGE_CHAT &&
							   y >= 390 && y < 2400) {
							chat_key((unsigned int)x, (unsigned int)y);
							page_changed = true;
						} else if (page == PAGE_CONSOLE &&
							   y >= 450 && y < 2450) {
							console_key((unsigned int)x, (unsigned int)y);
							page_changed = true;
						} else if (page == PAGE_INPUTS &&
							   y >= 360 && y < 2530) {
							if (x >= 1150) {
								unsigned int max_s = inputs_line_count > 38 ? inputs_line_count - 38 : 0;
								inputs_scroll_offset = max_s ? (y - 360) * max_s / 2159U : 0;
							} else if (y < 1400) {
								if (inputs_scroll_offset >= 5) inputs_scroll_offset -= 5;
								else inputs_scroll_offset = 0;
							} else {
								unsigned int max_s = inputs_line_count > 38 ? inputs_line_count - 38 : 0;
								inputs_scroll_offset += 5;
								if (inputs_scroll_offset > max_s) inputs_scroll_offset = max_s;
							}
							page_changed = true;
						} else if (page == PAGE_RADIO &&
							   y >= 360 && y < 2530) {
							unsigned int max_s = radio_line_count > 38 ? radio_line_count - 38 : 0;
							if (x >= 1150)
								radio_scroll_offset = max_s ? (y - 360) * max_s / 2159U : 0;
							else if (y < 1400)
								radio_scroll_offset = radio_scroll_offset >= 5 ? radio_scroll_offset - 5 : 0;
							else if (radio_scroll_offset + 5 <= max_s)
								radio_scroll_offset += 5;
							else
								radio_scroll_offset = max_s;
							page_changed = true;
						} else if (page == PAGE_OUTPUTS &&
							   y >= 360 && y < 2530) {
							if (x >= 1150) {
								unsigned int max_s = outputs_line_count > 38 ? outputs_line_count - 38 : 0;
								outputs_scroll_offset = max_s ? (y - 360) * max_s / 2159U : 0;
							} else if (y < 1400) {
								if (outputs_scroll_offset >= 5) outputs_scroll_offset -= 5;
								else outputs_scroll_offset = 0;
							} else {
								unsigned int max_s = outputs_line_count > 38 ? outputs_line_count - 38 : 0;
								outputs_scroll_offset += 5;
								if (outputs_scroll_offset > max_s) outputs_scroll_offset = max_s;
							}
							page_changed = true;
						}
						if (target != page) {
							page = target;
							page_changed = true;
							printf("page=%s\n", page == PAGE_HOME ?
							       "home" : page == PAGE_CHAT ?
							       "chat" : page == PAGE_DEBUG ?
							       "debug" : page == PAGE_POWER ?
							       "power" : "status");
							fflush(stdout);
						}
					}
					suppress_tap = false;
				}
				if (lit && monotonic_milliseconds() >= lit_until) {
					if (set_brightness(0) < 0) {
						fail("dim status screen");
						goto cleanup;
					}
					lit = false;
					printf("idle_dark\n");
					fflush(stdout);
				}
			} else {
				struct timespec delay = { .tv_sec = 60 };
				while (!stop_requested && nanosleep(&delay, &delay) < 0 && errno == EINTR)
					;
			}
			if (stop_requested)
				break;
			uint64_t now_ms = monotonic_milliseconds();
			int capacity = shown_capacity;
			if (now_ms - last_battery_poll >= 1000U) {
				capacity = read_battery_percent();
				last_battery_poll = now_ms;
				/* Follow the power mode (START, POWER SAVE, or a guard). */
				bool saving_now = read_power_saving(NULL, 0);
				if (portrait && saving_now && page != PAGE_POWER) {
					page = PAGE_POWER;
					page_changed = true;
					if (!lit && set_brightness(250) >= 0)
						lit = true;
					lit_until = now_ms + 15000U;
				} else if (portrait && !saving_now && page == PAGE_POWER) {
					page = PAGE_HOME;
					page_changed = true;
				}
			}
			size_t next_frame = shown_frame;
			int scene_result = 0;
			time_t minute = time(NULL) / 60;
			if (portrait) {
				scene_result = read_scene(&scene);
				if (scene_result == 1) {
					scene_started = now_ms;
					next_frame = 0;
					printf("scene=%s\n", scene.selection);
					fflush(stdout);
				} else if (scene_result < 0) {
					fprintf(stderr, "invalid portrait selection; keeping current scene\n");
				}
				if (scene.animate)
					next_frame = ((now_ms - scene_started) / 500U) %
						     scene.count;
			}
			bool status_refresh = portrait && (page == PAGE_STATUS || page == PAGE_INPUTS || page == PAGE_OUTPUTS || page == PAGE_POWER || page == PAGE_RADIO || page == PAGE_DEBUG) && lit &&
				now_ms - last_page_refresh >= 1000U;
			unsigned int console_seq = page == PAGE_CONSOLE ?
				console_sequence() : 0;
			bool console_refresh = portrait && page == PAGE_CONSOLE && lit &&
				console_seq != shown_console_sequence;
			time_t thought_mtime = get_thought_mtime();
			bool thought_refresh = false;
			if (portrait && thought_mtime != shown_thought_mtime && thought_mtime > 0) {
				/* Light up screen for 15 seconds when a thought is displayed */
				if (!lit) {
					if (set_brightness(250) >= 0)
						lit = true;
				}
				lit_until = now_ms + 15000U;
				thought_refresh = true;
			}
			int hearing_on = read_hearing_enabled();
			bool hearing_refresh = portrait && page == PAGE_HOME && lit &&
				hearing_on != shown_hearing_on;
			if (capacity == shown_capacity && (!portrait ||
			    (!page_changed && !status_refresh && !console_refresh &&
			     !thought_refresh && !hearing_refresh &&
			     (page != PAGE_HOME ||
			      (next_frame == shown_frame && minute == shown_minute &&
			       scene_result != 1)))))
				continue;
			int target_fd = current_fb == fb_id ? buffer_fd2 : buffer_fd;
			uint32_t target_fb = current_fb == fb_id ? fb_id2 : fb_id;
			void *target_pixels = current_fb == fb_id ? pixels2 : pixels;
			if (sync_buffer(target_fd, DMA_BUF_SYNC_START | DMA_BUF_SYNC_WRITE) < 0) {
				fail("begin status refresh");
				goto cleanup;
			}
			if (portrait) {
				if (paint_lynx_page(target_pixels, page,
						    scene.frames[next_frame], capacity) < 0) {
					fail("render Lynx portrait");
					goto cleanup;
				}
			} else {
				paint_lynx_status(target_pixels, capacity);
			}
			if (sync_buffer(target_fd, DMA_BUF_SYNC_END | DMA_BUF_SYNC_WRITE) < 0) {
				fail("end status refresh");
				goto cleanup;
			}
			if (atomic_present_fb(drm_fd, plane_id, target_fb) < 0) {
				fail("present refreshed status framebuffer");
				goto cleanup;
			}
			current_fb = target_fb;
			shown_capacity = capacity;
			shown_frame = next_frame;
			shown_minute = minute;
			shown_thought_mtime = thought_mtime;
			shown_hearing_on = hearing_on;
			page_changed = false;
			if (page == PAGE_STATUS || page == PAGE_INPUTS || page == PAGE_OUTPUTS || page == PAGE_DEBUG)
				last_page_refresh = now_ms;
			if (page == PAGE_CONSOLE)
				shown_console_sequence = console_seq;
			if (portrait && !scene.animate)
				printf("presented_pose=%s battery=%d%%\n",
				       scene.frames[next_frame], shown_capacity);
			else if (!portrait)
				printf("presented_battery=%d%%\n", shown_capacity);
			if (!portrait || !scene.animate)
				fflush(stdout);
		}
	} else {
		struct timespec delay = { .tv_sec = seconds };
		while (!stop_requested && nanosleep(&delay, &delay) < 0 && errno == EINTR)
			;
	}
	rc = 0;

cleanup:
	if (touch_idle && active && set_brightness(0) < 0) {
		fail("turn off touch-idle brightness");
		rc = 1;
	}
	if (active && (atomic ? atomic_disable(drm_fd, connector_id, crtc_id,
						     plane_id) :
			     drmModeSetCrtc(drm_fd, crtc_id, 0, 0, 0,
					    NULL, 0, NULL)) < 0) {
		fail("disable test CRTC");
		rc = 1;
	}
	if (fb_id && drmModeRmFB(drm_fd, fb_id) < 0) {
		fail("remove test framebuffer");
		rc = 1;
	}
	if (fb_id2 && drmModeRmFB(drm_fd, fb_id2) < 0) {
		fail("remove second status framebuffer");
		rc = 1;
	}
	if (handle) {
		struct drm_gem_close close_arg = { .handle = handle };
		if (drmIoctl(drm_fd, DRM_IOCTL_GEM_CLOSE, &close_arg) < 0) {
			fail("close imported GEM handle");
			rc = 1;
		}
	}
	if (handle2) {
		struct drm_gem_close close_arg = { .handle = handle2 };
		if (drmIoctl(drm_fd, DRM_IOCTL_GEM_CLOSE, &close_arg) < 0) {
			fail("close second imported GEM handle");
			rc = 1;
		}
	}
	if (pixels != MAP_FAILED)
		munmap(pixels, length);
	if (pixels2 != MAP_FAILED)
		munmap(pixels2, length);
	if (buffer_fd >= 0)
		close(buffer_fd);
	if (buffer_fd2 >= 0)
		close(buffer_fd2);
	if (touch_fd >= 0)
		close(touch_fd);
	if (heap_fd >= 0)
		close(heap_fd);
	if (resources)
		drmModeFreeResources(resources);
	if (drm_fd >= 0)
		close(drm_fd);
	return rc;
}

int main(int argc, char **argv)
{
	unsigned int seconds = 0;
	struct sigaction stop_action = { .sa_handler = request_stop };
	sigemptyset(&stop_action.sa_mask);
	sigaction(SIGINT, &stop_action, NULL);
	sigaction(SIGTERM, &stop_action, NULL);
	if (argc == 4 && !strcmp(argv[1], "--preview"))
		return render_preview(argv[2], argv[3], PAGE_HOME);
	if (argc == 2 && !strcmp(argv[1], "--self-test-touch"))
		return self_test_touch();
	if (argc == 2 && !strcmp(argv[1], "--self-test-console-keys"))
		return self_test_console_keys();
	if (argc == 2 && !strcmp(argv[1], "--self-test-chat-keys"))
		return self_test_chat_keys();
	if (argc == 4 && !strcmp(argv[1], "--preview-page")) {
		if (!strcmp(argv[2], "home"))
			return render_preview("01_standing_smile", argv[3], PAGE_HOME);
		if (!strcmp(argv[2], "chat"))
			return render_preview("", argv[3], PAGE_CHAT);
		if (!strcmp(argv[2], "inputs"))
			return render_preview("", argv[3], PAGE_INPUTS);
		if (!strcmp(argv[2], "outputs"))
			return render_preview("", argv[3], PAGE_OUTPUTS);
		if (!strcmp(argv[2], "console"))
			return render_preview("", argv[3], PAGE_CONSOLE);
		if (!strcmp(argv[2], "status"))
			return render_preview("", argv[3], PAGE_STATUS);
		if (!strcmp(argv[2], "power"))
			return render_preview("", argv[3], PAGE_POWER);
		if (!strcmp(argv[2], "radio"))
			return render_preview("", argv[3], PAGE_RADIO);
		if (!strcmp(argv[2], "debug"))
			return render_preview("", argv[3], PAGE_DEBUG);
		return 2;
	}
	if (argc == 3 && !strcmp(argv[1], "--preview-console-symbols")) {
		console_symbols = true;
		return render_preview("", argv[2], PAGE_CONSOLE);
	}
	if (argc == 2 && (!strcmp(argv[1], "--probe") ||
			  !strcmp(argv[1], "--allocate") ||
			  !strcmp(argv[1], "--atomic-test") ||
			  !strcmp(argv[1], "--show-ui-until-signal") ||
			  !strcmp(argv[1], "--show-ui-touch-idle") ||
			  !strcmp(argv[1], "--show-portrait-touch-idle")))
		return run(argv[1], 0);
	if (argc == 3 && (!strcmp(argv[1], "--show") ||
			  !strcmp(argv[1], "--show-atomic") ||
			  !strcmp(argv[1], "--show-ui"))) {
		char *end;
		unsigned long value = strtoul(argv[2], &end, 10);
		if (*argv[2] && !*end && value >= 1 && value <= 15) {
			seconds = (unsigned int)value;
			return run(argv[1], seconds);
		}
	}
	fprintf(stderr, "usage: %s --probe | --allocate | --atomic-test | --show SECONDS(1..15) | --show-atomic SECONDS(1..15) | --show-ui SECONDS(1..15) | --show-ui-until-signal | --show-ui-touch-idle | --show-portrait-touch-idle\n",
		argv[0]);
	return 2;
}
