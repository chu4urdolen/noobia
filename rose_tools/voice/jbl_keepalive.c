#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define DEFAULT_TARGET "bluez_output.54_15_89_73_C2_95.1"

static volatile sig_atomic_t running = 1;
static volatile sig_atomic_t player_pid = -1;

static void stop(int signal_number)
{
    (void)signal_number;
    running = 0;
    if (player_pid > 0) (void)kill((pid_t)player_pid, SIGTERM);
}

static const char *setting(const char *name, const char *fallback)
{
    const char *value = getenv(name);
    return value != NULL && *value != '\0' ? value : fallback;
}

int main(void)
{
    const char *player = setting("ROSE_PW_PLAY_BIN", "/usr/bin/pw-play");
    const char *target = setting("ROSE_JBL_TARGET", DEFAULT_TARGET);
    int audio_pipe[2];
    pid_t child;
    int status = 0;
    int16_t silence[960 * 2] = {0};

    signal(SIGINT, stop);
    signal(SIGTERM, stop);
    signal(SIGPIPE, SIG_IGN);
    if (pipe(audio_pipe) != 0) { perror("pipe"); return EXIT_FAILURE; }
    child = fork();
    if (child < 0) { perror("fork"); return EXIT_FAILURE; }
    if (child == 0) {
        char *const arguments[] = {
            (char *)player, "--playback", "--raw", "--target", (char *)target,
            "--rate", "48000", "--channels", "2", "--channel-map", "stereo",
            "--format", "s16", "--latency", "100ms", "-", NULL
        };
        if (dup2(audio_pipe[0], STDIN_FILENO) < 0) _exit(126);
        close(audio_pipe[0]);
        close(audio_pipe[1]);
        execv(player, arguments);
        _exit(errno == ENOENT ? 127 : 126);
    }
    player_pid = child;
    close(audio_pipe[0]);
    fprintf(stderr, "JBL keepalive streaming silence to %s\n", target);
    while (running) {
        const unsigned char *cursor = (const unsigned char *)silence;
        size_t remaining = sizeof(silence);
        while (remaining > 0 && running) {
            ssize_t count = write(audio_pipe[1], cursor, remaining);
            if (count < 0) {
                if (errno == EINTR) continue;
                running = 0;
                break;
            }
            cursor += count;
            remaining -= (size_t)count;
        }
    }
    close(audio_pipe[1]);
    while (waitpid(child, &status, 0) < 0 && errno == EINTR) {}
    player_pid = -1;
    if (!running && (WIFEXITED(status) || WIFSIGNALED(status))) return EXIT_SUCCESS;
    return EXIT_FAILURE;
}
