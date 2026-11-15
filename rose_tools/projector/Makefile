CC ?= cc
CFLAGS ?= -O2 -std=c11 -Wall -Wextra -Wpedantic -Werror
LDFLAGS ?=
USER_PREFIX ?= $(HOME)/.local

.PHONY: all clean install-user

all: projector-cast

projector-cast: projector_cast.c
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ projector_cast.c

install-user: projector-cast
	install -d $(USER_PREFIX)/bin
	install -m 0755 projector-cast $(USER_PREFIX)/bin/projector-cast

clean:
	rm -f projector-cast
