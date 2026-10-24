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

static int run(const char *action, unsigned int seconds)
{
	int drm_fd = -1, heap_fd = -1, buffer_fd = -1, rc = 1;
	void *pixels = MAP_FAILED;
	uint32_t handle = 0, fb_id = 0, connector_id = 0, crtc_id = 0;
	drmModeRes *resources = NULL;
	drmModeModeInfo mode = { 0 };
	bool active = false;
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
	if (drmModeSetCrtc(drm_fd, crtc_id, fb_id, 0, 0,
			   &connector_id, 1, &mode) < 0) {
		fail("set DSI CRTC");
		goto cleanup;
	}
	active = true;
	printf("displaying color bars for %u seconds\n", seconds);
	fflush(stdout);
	struct timespec delay = { .tv_sec = seconds };
	while (!stop_requested && nanosleep(&delay, &delay) < 0 && errno == EINTR)
		;
	rc = 0;

cleanup:
	if (active && drmModeSetCrtc(drm_fd, crtc_id, 0, 0, 0,
				    NULL, 0, NULL) < 0) {
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
			  !strcmp(argv[1], "--allocate")))
		return run(argv[1], 0);
	if (argc == 3 && !strcmp(argv[1], "--show")) {
		char *end;
		unsigned long value = strtoul(argv[2], &end, 10);
		if (*argv[2] && !*end && value >= 1 && value <= 15) {
			seconds = (unsigned int)value;
			return run(argv[1], seconds);
		}
	}
	fprintf(stderr, "usage: %s --probe | --allocate | --show SECONDS(1..15)\n",
		argv[0]);
	return 2;
}
