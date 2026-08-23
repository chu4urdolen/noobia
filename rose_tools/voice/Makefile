CC ?= cc
CFLAGS ?= -O2
CFLAGS += -std=c11 -Wall -Wextra -Wpedantic -Werror
LDLIBS += -lm -pthread

USER_PREFIX ?= $(HOME)/.local

.PHONY: all clean install-user

all: rose-voice

rose-voice: rose_voice.c ../hue/hue_client.c ../hue/hue_client.h
	$(CC) $(CFLAGS) -I../hue $(LDFLAGS) -o $@ rose_voice.c ../hue/hue_client.c $(LDLIBS)

install-user: rose-voice
	install -d $(USER_PREFIX)/bin $(USER_PREFIX)/libexec
	install -m 0755 rose-voice $(USER_PREFIX)/libexec/rose-voice
	install -m 0755 rose-say $(USER_PREFIX)/bin/rose-say

clean:
	rm -f rose-voice
