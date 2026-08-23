CC ?= cc
CFLAGS ?= -O2
CFLAGS += -std=c11 -Wall -Wextra -Wpedantic -Werror
LDLIBS += -lm
USER_PREFIX ?= $(HOME)/.local

.PHONY: all clean install-user

all: rose-hue rose-hue-off

rose-hue: rose_hue.c hue_client.c hue_client.h
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ rose_hue.c hue_client.c $(LDLIBS)

rose-hue-off: rose_hue_off.c hue_client.c hue_client.h
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ rose_hue_off.c hue_client.c $(LDLIBS)

install-user: rose-hue rose-hue-off
	install -d $(USER_PREFIX)/bin $(HOME)/.config/systemd/user
	install -m 0755 rose-hue $(USER_PREFIX)/bin/rose-hue
	install -m 0755 rose-hue-off $(USER_PREFIX)/bin/rose-hue-off
	install -m 0644 rose-hue-shutdown.service $(HOME)/.config/systemd/user/rose-hue-shutdown.service

clean:
	rm -f rose-hue rose-hue-off
