#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L

#include "camera_common.h"

#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

const char *camera_setting(const char *name, const char *fallback)
{
    const char *value = getenv(name);
    return value != NULL && *value != '\0' ? value : fallback;
}

int camera_temp_path(char *path, size_t size, const char *kind, const char *suffix)
{
    int length = snprintf(path, size, "/tmp/rose-nyx-%s-XXXXXX%s", kind, suffix);
    int descriptor;
    if (length < 0 || (size_t)length >= size) return -1;
    descriptor = mkstemps(path, (int)strlen(suffix));
    if (descriptor < 0) return -1;
    close(descriptor);
    return 0;
}

int camera_run(char *const arguments[], unsigned int timeout_seconds)
{
    pid_t child = fork();
    int status;
    struct timespec start, now, pause = {0, 50000000L};
    if (child < 0) return -1;
    if (child == 0) {
        (void)setpgid(0, 0);
        execv(arguments[0], arguments);
        _exit(errno == ENOENT ? 127 : 126);
    }
    clock_gettime(CLOCK_MONOTONIC, &start);
    for (;;) {
        pid_t result = waitpid(child, &status, WNOHANG);
        if (result == child)
            return WIFEXITED(status) && WEXITSTATUS(status) == 0 ? 0 : -1;
        if (result < 0 && errno != EINTR) return -1;
        clock_gettime(CLOCK_MONOTONIC, &now);
        long long elapsed = (long long)(now.tv_sec - start.tv_sec) * 1000LL +
                            (now.tv_nsec - start.tv_nsec) / 1000000L;
        if (elapsed >= (long long)timeout_seconds * 1000LL) {
            fprintf(stderr, "Nyx camera command timed out after %u seconds\n", timeout_seconds);
            (void)kill(-child, SIGKILL);
            (void)kill(child, SIGKILL);
            while (waitpid(child, &status, 0) < 0 && errno == EINTR) {}
            return -1;
        }
        nanosleep(&pause, NULL);
    }
}

int camera_file_ready(const char *path)
{
    struct stat details;
    return stat(path, &details) == 0 && S_ISREG(details.st_mode) && details.st_size > 0;
}
