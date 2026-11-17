CC ?= cc
CFLAGS ?= -O2
CFLAGS += -std=c11 -Wall -Wextra -Wpedantic -Werror
LDLIBS += -lm -pthread

USER_PREFIX ?= $(HOME)/.local

.PHONY: all clean install-user

COUNCIL_ROOT := ../..
COUNCIL_SOURCES := $(COUNCIL_ROOT)/src/authentication.c $(COUNCIL_ROOT)/src/contact_book.c \
	$(COUNCIL_ROOT)/src/file_storage.c $(COUNCIL_ROOT)/src/network.c \
	$(COUNCIL_ROOT)/src/protocol.c $(COUNCIL_ROOT)/src/sha256.c
COUNCIL_CFLAGS := -I$(COUNCIL_ROOT)/include

all: rose-voice rose-voice-worker rose-jbl-keepalive

rose-voice: rose_voice.c voice_stage.c voice_remote.c voice_stage.h voice_remote.h ../hue/hue_client.c ../hue/hue_client.h $(COUNCIL_SOURCES)
	$(CC) $(CFLAGS) -I../hue $(COUNCIL_CFLAGS) $(LDFLAGS) -o $@ rose_voice.c voice_stage.c voice_remote.c ../hue/hue_client.c $(COUNCIL_SOURCES) $(LDLIBS)

rose-voice-worker: voice_worker.c voice_stage.c voice_stage.h $(COUNCIL_SOURCES)
	$(CC) $(CFLAGS) $(COUNCIL_CFLAGS) $(LDFLAGS) -o $@ voice_worker.c voice_stage.c $(COUNCIL_SOURCES) $(LDLIBS)

rose-jbl-keepalive: jbl_keepalive.c
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ jbl_keepalive.c

install-user: rose-voice rose-voice-worker rose-jbl-keepalive
	install -d $(USER_PREFIX)/bin $(USER_PREFIX)/libexec $(HOME)/.config/systemd/user
	install -m 0755 rose-voice $(USER_PREFIX)/libexec/rose-voice
	install -m 0755 rose-voice-worker $(USER_PREFIX)/libexec/rose-voice-worker
	install -m 0755 rose-jbl-keepalive $(USER_PREFIX)/libexec/rose-jbl-keepalive
	install -m 0755 rose-say $(USER_PREFIX)/bin/rose-say
	install -m 0755 rose-voice-worker-launch $(USER_PREFIX)/bin/rose-voice-worker-launch
	install -m 0644 rose-voice-worker@.service $(HOME)/.config/systemd/user/rose-voice-worker@.service
	install -m 0644 rose-jbl-keepalive.service $(HOME)/.config/systemd/user/rose-jbl-keepalive.service

clean:
	rm -f rose-voice rose-voice-worker rose-jbl-keepalive
