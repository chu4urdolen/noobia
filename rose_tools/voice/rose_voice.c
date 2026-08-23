#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define DEFAULT_PIPER "/home/rose/piper/bin/piper-tts/piper"
#define DEFAULT_VOICE "/home/rose/piper/voices/en_GB/cori/high/en_GB-cori-high.onnx"
#define DEFAULT_SINK "@DEFAULT_AUDIO_SINK@"

static const char *env_or_default(const char *name, const char *fallback)
{
    const char *value = getenv(name);
    return value != NULL && *value != '\0' ? value : fallback;
}

static int wait_for_child(pid_t pid, const char *name)
{
    int status;

    while (waitpid(pid, &status, 0) < 0) {
        if (errno == EINTR) continue;
        perror("waitpid");
        return -1;
    }
    if (WIFEXITED(status) && WEXITSTATUS(status) == 0) return 0;
    if (WIFEXITED(status)) {
        fprintf(stderr, "%s exited with status %d\n", name, WEXITSTATUS(status));
    } else if (WIFSIGNALED(status)) {
        fprintf(stderr, "%s terminated by signal %d\n", name, WTERMSIG(status));
    }
    return -1;
}

static int run_with_input(char *const argv[], const char *input)
{
    int input_pipe[2];
    pid_t pid;
    size_t remaining = strlen(input);
    const char *cursor = input;

    if (pipe(input_pipe) != 0) {
        perror("pipe");
        return -1;
    }
    pid = fork();
    if (pid < 0) {
        perror("fork");
        close(input_pipe[0]);
        close(input_pipe[1]);
        return -1;
    }
    if (pid == 0) {
        if (dup2(input_pipe[0], STDIN_FILENO) < 0) _exit(126);
        close(input_pipe[0]);
        close(input_pipe[1]);
        execv(argv[0], argv);
        perror(argv[0]);
        _exit(errno == ENOENT ? 127 : 126);
    }
    close(input_pipe[0]);
    while (remaining > 0) {
        ssize_t written = write(input_pipe[1], cursor, remaining);
        if (written < 0) {
            if (errno == EINTR) continue;
            perror("write");
            close(input_pipe[1]);
            (void)wait_for_child(pid, argv[0]);
            return -1;
        }
        cursor += written;
        remaining -= (size_t)written;
    }
    close(input_pipe[1]);
    return wait_for_child(pid, argv[0]);
}

static int run_command(char *const argv[])
{
    pid_t pid = fork();

    if (pid < 0) {
        perror("fork");
        return -1;
    }
    if (pid == 0) {
        execvp(argv[0], argv);
        perror(argv[0]);
        _exit(errno == ENOENT ? 127 : 126);
    }
    return wait_for_child(pid, argv[0]);
}

static char *join_arguments(int argc, char **argv)
{
    size_t length = 1;
    char *text;
    char *cursor;

    for (int i = 1; i < argc; i++) {
        if (strlen(argv[i]) > SIZE_MAX - length - 1) return NULL;
        length += strlen(argv[i]) + 1;
    }
    text = malloc(length);
    if (text == NULL) return NULL;
    cursor = text;
    for (int i = 1; i < argc; i++) {
        size_t part_length = strlen(argv[i]);
        memcpy(cursor, argv[i], part_length);
        cursor += part_length;
        if (i + 1 < argc) *cursor++ = ' ';
    }
    *cursor = '\0';
    return text;
}

static int temporary_wav(char *path, size_t size, const char *kind)
{
    int result = snprintf(path, size, "/tmp/rose-voice-%s-XXXXXX.wav", kind);
    int descriptor;

    if (result < 0 || (size_t)result >= size) return -1;
    descriptor = mkstemps(path, 4);
    if (descriptor < 0) return -1;
    close(descriptor);
    return 0;
}

int main(int argc, char **argv)
{
    const char *piper = env_or_default("ROSE_PIPER_BIN", DEFAULT_PIPER);
    const char *voice = env_or_default("ROSE_PIPER_VOICE", DEFAULT_VOICE);
    const char *sox = env_or_default("ROSE_SOX_BIN", "sox");
    const char *sink = env_or_default("ROSE_AUDIO_SINK", DEFAULT_SINK);
    char dry_path[PATH_MAX] = "";
    char wet_path[PATH_MAX] = "";
    char pitch[16];
    char *text;
    int result = EXIT_FAILURE;

    if (argc < 2) {
        fprintf(stderr, "Usage: %s TEXT...\n", argv[0]);
        return EXIT_FAILURE;
    }
    text = join_arguments(argc, argv);
    if (text == NULL || *text == '\0') {
        fprintf(stderr, "Could not build speech text\n");
        free(text);
        return EXIT_FAILURE;
    }
    if (access(piper, X_OK) != 0 || access(voice, R_OK) != 0) {
        fprintf(stderr, "Piper binary or voice model is unavailable\n");
        goto cleanup;
    }
    if (temporary_wav(dry_path, sizeof(dry_path), "dry") != 0 ||
        temporary_wav(wet_path, sizeof(wet_path), "fx") != 0) {
        perror("temporary file");
        goto cleanup;
    }

    char *piper_argv[] = {(char *)piper, "--model", (char *)voice,
                          "--output_file", dry_path, NULL};
    if (run_with_input(piper_argv, text) != 0) goto cleanup;

    srand((unsigned int)(time(NULL) ^ getpid()));
    snprintf(pitch, sizeof(pitch), "%d", -(10 + rand() % 151));
    char *sox_argv[] = {
        (char *)sox, dry_path, wet_path,
        "gain", "-3", "pitch", pitch,
        "chorus", "0.5", "0.9", "50", "0.4", "0.25", "2", "-t",
        "60", "0.32", "0.4", "2.3", "-t",
        "40", "0.3", "0.3", "1.3", "-s",
        "reverse", "reverb", "80", "50", "100", "100", "25", "-1",
        "reverse", NULL
    };
    if (run_command(sox_argv) != 0) goto cleanup;

    char *play_argv[] = {"pw-play", "--target", (char *)sink, wet_path, NULL};
    if (run_command(play_argv) != 0) goto cleanup;
    result = EXIT_SUCCESS;

cleanup:
    if (*wet_path != '\0') unlink(wet_path);
    if (*dry_path != '\0') unlink(dry_path);
    free(text);
    return result;
}
