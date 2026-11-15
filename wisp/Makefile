CC ?= cc
CFLAGS ?= -O2 -pipe
CFLAGS += -std=c11 -Wall -Wextra -Wpedantic -D_FORTIFY_SOURCE=2
LDLIBS += -lutil -pthread

.PHONY: all clean test
all: wisp-web
wisp-web: server.c
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $< $(LDLIBS)
clean:
	rm -f wisp-web
test: wisp-web
	./test.sh
