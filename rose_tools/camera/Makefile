CC ?= cc
CFLAGS ?= -O2 -std=c11 -Wall -Wextra -Wpedantic -Werror
LDFLAGS ?=
USER_PREFIX ?= $(HOME)/.local

.PHONY: all clean install-user

all: rose-nyx-snapshot rose-nyx-detect

rose-nyx-snapshot: rose_snapshot.c camera_common.c camera_common.h
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ rose_snapshot.c camera_common.c

rose-nyx-detect: rose_detect.c camera_common.c camera_common.h
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ rose_detect.c camera_common.c

install-user: all
	install -d $(USER_PREFIX)/bin $(USER_PREFIX)/share/rose-tools/camera
	install -m 0755 rose-nyx-snapshot $(USER_PREFIX)/bin/rose-nyx-snapshot
	install -m 0755 rose-nyx-detect $(USER_PREFIX)/bin/rose-nyx-detect
	install -m 0644 imx500_mobilenet_ssd.json $(USER_PREFIX)/share/rose-tools/camera/imx500_mobilenet_ssd.json
	install -m 0644 imx500_posenet.json $(USER_PREFIX)/share/rose-tools/camera/imx500_posenet.json

clean:
	rm -f rose-nyx-snapshot rose-nyx-detect
