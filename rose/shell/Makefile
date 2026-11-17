CC ?= cc
CFLAGS ?= -O2 -std=c11 -Wall -Wextra -Wpedantic -Werror

rose-shell: rose_shell.c
	$(CC) $(CFLAGS) -o $@ $<

install-user: rose-shell
	install -D -m 0755 rose-shell $(HOME)/.local/bin/rose-shell

.PHONY: install-user
