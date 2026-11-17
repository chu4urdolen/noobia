#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* stdout/stderr are inherited so the agent runner can capture both.
 * This process deliberately retains the calling user's ordinary permissions. */
int main(int argc, char **argv) {
    char buffer[32769];
    const char *command = NULL;
    if (argc == 3 && strcmp(argv[1], "-c") == 0) {
        command = argv[2];
    } else if (argc == 1) {
        size_t used = fread(buffer, 1, sizeof(buffer) - 1, stdin);
        if (ferror(stdin) || (used == sizeof(buffer) - 1 && fgetc(stdin) != EOF)) {
            fprintf(stderr, "rose-shell: command exceeds 32768 bytes or input failed\n");
            return 2;
        }
        buffer[used] = '\0';
        if (memchr(buffer, '\0', used) != NULL) {
            fprintf(stderr, "rose-shell: command contains a NUL byte\n");
            return 2;
        }
        command = buffer;
    } else {
        fprintf(stderr, "usage: rose-shell -c 'command' | rose-shell < command-file\n");
        return 2;
    }
    if (!command[0]) {
        fprintf(stderr, "rose-shell: empty command\n");
        return 2;
    }
    execl("/bin/sh", "sh", "-c", command, (char *)NULL);
    fprintf(stderr, "rose-shell: cannot start shell: %s\n", strerror(errno));
    return 127;
}
