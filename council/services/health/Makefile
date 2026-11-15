CC ?= cc
CFLAGS ?= -O2
CFLAGS += -std=c11 -Wall -Wextra -Wpedantic
PREFIX ?= /usr/local
LIBEXECDIR ?= $(PREFIX)/libexec
SYSTEMD_UNIT_DIR ?= /etc/systemd/system
DOCDIR ?= $(PREFIX)/share/doc/noobia-health

.PHONY: all clean install uninstall

all: noobia-health

noobia-health: health.c
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $<

install: noobia-health
	install -d $(DESTDIR)$(LIBEXECDIR) $(DESTDIR)$(SYSTEMD_UNIT_DIR) $(DESTDIR)$(DOCDIR)
	install -m 0755 noobia-health $(DESTDIR)$(LIBEXECDIR)/noobia-health
	install -m 0644 noobia-health.service $(DESTDIR)$(SYSTEMD_UNIT_DIR)/noobia-health.service
	install -m 0644 README.md $(DESTDIR)$(DOCDIR)/README.md

uninstall:
	rm -f $(DESTDIR)$(LIBEXECDIR)/noobia-health
	rm -f $(DESTDIR)$(SYSTEMD_UNIT_DIR)/noobia-health.service
	rm -f $(DESTDIR)$(DOCDIR)/README.md

clean:
	rm -f noobia-health
