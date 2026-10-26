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
#include <fcntl.h>
#include <inttypes.h>
#include <linux/dma-buf.h>
#include <linux/dma-heap.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <drm_fourcc.h>

#define WIDTH 1240U
#define HEIGHT 2772U
#define STRIDE (WIDTH * 4U)
#define HEAP_DEVICE "/dev/dma_heap/system"
#define DRM_DEVICE "/dev/dri/card0"

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
	{'E', {0x1f, 0x10, 0x10, 0x1e, 0x10, 0x10, 0x1f}},
	{'I', {0x0e, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0e}},
	{'L', {0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1f}},
	{'N', {0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11}},
	{'P', {0x1e, 0x11, 0x11, 0x1e, 0x10, 0x10, 0x10}},
	{'R', {0x1e, 0x11, 0x11, 0x1e, 0x14, 0x12, 0x11}},
	{'T', {0x1f, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04}},
	{'U', {0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0e}},
	{'V', {0x11, 0x11, 0x11, 0x11, 0x0a, 0x0a, 0x04}},
	{'X', {0x11, 0x11, 0x0a, 0x04, 0x0a, 0x11, 0x11}},
	{'Y', {0x11, 0x11, 0x0a, 0x04, 0x04, 0x04, 0x04}},
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
	draw_text(pixels, "ALPINE", 384, 2050, 14, white);
	rectangle(pixels, 0, HEIGHT - 36, WIDTH, 36, teal);
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

static int run(const char *action, unsigned int seconds)
{
	int drm_fd = -1, heap_fd = -1, buffer_fd = -1, rc = 1;
	void *pixels = MAP_FAILED;
	uint32_t handle = 0, fb_id = 0, connector_id = 0, crtc_id = 0, plane_id = 0;
	drmModeRes *resources = NULL;
	drmModeModeInfo mode = { 0 };
	bool active = false;
	bool persistent_ui = !strcmp(action, "--show-ui-until-signal");
	bool atomic = !strcmp(action, "--atomic-test") ||
		!strcmp(action, "--show-atomic") || !strcmp(action, "--show-ui") ||
		persistent_ui;
	bool ui = !strcmp(action, "--show-ui") || persistent_ui;
	int shown_capacity = -1;
	uint64_t prime_caps = 0;
	const size_t length = ((size_t)STRIDE * HEIGHT + 4095U) & ~(size_t)4095U;

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
		paint_lynx_status(pixels, shown_capacity);
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
	if (persistent_ui)
		printf("displaying Lynx status until signal\n");
	else
		printf("displaying %s for %u seconds\n",
		       ui ? "Lynx status" : "color bars", seconds);
	fflush(stdout);
	if (persistent_ui) {
		while (!stop_requested) {
			struct timespec delay = { .tv_sec = 60 };
			while (!stop_requested && nanosleep(&delay, &delay) < 0 && errno == EINTR)
				;
			if (stop_requested)
				break;
			int capacity = read_battery_percent();
			if (capacity == shown_capacity)
				continue;
			if (sync_buffer(buffer_fd, DMA_BUF_SYNC_START | DMA_BUF_SYNC_WRITE) < 0) {
				fail("begin status refresh");
				rc = 1;
				goto cleanup;
			}
			paint_lynx_status(pixels, capacity);
			if (sync_buffer(buffer_fd, DMA_BUF_SYNC_END | DMA_BUF_SYNC_WRITE) < 0) {
				fail("end status refresh");
				rc = 1;
				goto cleanup;
			}
			shown_capacity = capacity;
			printf("battery=%d%%\n", shown_capacity);
			fflush(stdout);
		}
	} else {
		struct timespec delay = { .tv_sec = seconds };
		while (!stop_requested && nanosleep(&delay, &delay) < 0 && errno == EINTR)
			;
	}
	rc = 0;

cleanup:
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
	if (handle) {
		struct drm_gem_close close_arg = { .handle = handle };
		if (drmIoctl(drm_fd, DRM_IOCTL_GEM_CLOSE, &close_arg) < 0) {
			fail("close imported GEM handle");
			rc = 1;
		}
	}
	if (pixels != MAP_FAILED)
		munmap(pixels, length);
	if (buffer_fd >= 0)
		close(buffer_fd);
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
	if (argc == 2 && (!strcmp(argv[1], "--probe") ||
			  !strcmp(argv[1], "--allocate") ||
			  !strcmp(argv[1], "--atomic-test") ||
			  !strcmp(argv[1], "--show-ui-until-signal")))
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
	fprintf(stderr, "usage: %s --probe | --allocate | --atomic-test | --show SECONDS(1..15) | --show-atomic SECONDS(1..15) | --show-ui SECONDS(1..15) | --show-ui-until-signal\n",
		argv[0]);
	return 2;
}
