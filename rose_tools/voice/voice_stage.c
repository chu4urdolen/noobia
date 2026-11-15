#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L

#include "voice_stage.h"

#include <errno.h>
#include <math.h>
#include <signal.h>
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
#define ENVELOPE_HOP 0.125

static const char *setting(const char *name, const char *fallback)
{
    const char *value = getenv(name);
    return value != NULL && *value != '\0' ? value : fallback;
}

static unsigned int stage_timeout_seconds(void)
{
    const char *text = setting("ROSE_STAGE_TIMEOUT_SECONDS", "120");
    char *end;
    unsigned long value = strtoul(text, &end, 10);
    return end != text && *end == '\0' && value >= 1 && value <= 3600 ?
           (unsigned int)value : 120U;
}

static int wait_child(pid_t pid)
{
    int status;
    struct timespec start, now, pause = {0, 50000000L};
    unsigned int timeout = stage_timeout_seconds();
    clock_gettime(CLOCK_MONOTONIC, &start);
    for (;;) {
        pid_t result = waitpid(pid, &status, WNOHANG);
        if (result == pid)
            return WIFEXITED(status) && WEXITSTATUS(status) == 0 ? 0 : -1;
        if (result < 0 && errno != EINTR) return -1;
        clock_gettime(CLOCK_MONOTONIC, &now);
        long long elapsed_ms = (long long)(now.tv_sec - start.tv_sec) * 1000LL +
                               (now.tv_nsec - start.tv_nsec) / 1000000L;
        if (elapsed_ms >= (long long)timeout * 1000LL) {
            fprintf(stderr, "voice stage timed out after %u seconds\n", timeout);
            (void)kill(-pid, SIGKILL);
            (void)kill(pid, SIGKILL);
            while (waitpid(pid, &status, 0) < 0 && errno == EINTR) {}
            return -1;
        }
        nanosleep(&pause, NULL);
    }
}

static int run(char *const argv[], int input_fd)
{
    pid_t pid = fork();
    if (pid < 0) return -1;
    if (pid == 0) {
        (void)setpgid(0, 0);
        if (input_fd >= 0 && dup2(input_fd, STDIN_FILENO) < 0) _exit(126);
        execv(argv[0], argv);
        _exit(127);
    }
    return wait_child(pid);
}

int voice_stage_piper(const char *text_path, const char *output_path)
{
    const char *piper = setting("ROSE_PIPER_BIN", DEFAULT_PIPER);
    const char *voice = setting("ROSE_PIPER_VOICE", DEFAULT_VOICE);
    FILE *input = fopen(text_path, "rb");
    if (input == NULL) return -1;
    char *argv[] = {(char *)piper, "--model", (char *)voice,
                    "--output_file", (char *)output_path, NULL};
    int result = run(argv, fileno(input));
    fclose(input);
    return result;
}

int voice_stage_sox(const char *input_path, const char *output_path)
{
    const char *sox = setting("ROSE_SOX_BIN", "sox");
    char pitch[16];
    snprintf(pitch, sizeof(pitch), "%d", -(10 + rand() % 151));
    char *argv[] = {
        (char *)sox, (char *)input_path, (char *)output_path,
        "gain", "-3", "pitch", pitch,
        "chorus", "0.5", "0.9", "50", "0.4", "0.25", "2", "-t",
        "60", "0.32", "0.4", "2.3", "-t", "40", "0.3", "0.3", "1.3", "-s",
        "reverse", "reverb", "80", "50", "100", "100", "25", "-1", "reverse", NULL};
    return run(argv, -1);
}

static unsigned int le16(const unsigned char *p) { return p[0] | ((unsigned int)p[1] << 8); }
static unsigned int le32(const unsigned char *p) { return p[0] | ((unsigned int)p[1] << 8) | ((unsigned int)p[2] << 16) | ((unsigned int)p[3] << 24); }

static int wav_levels(const char *path, unsigned char **levels, size_t *count)
{
    FILE *file = fopen(path, "rb");
    unsigned char header[12], chunk[8], format[16], *data = NULL, *result = NULL;
    unsigned int channels = 0, rate = 0, bits = 0, data_size = 0;
    long offset = 0;
    if (file == NULL || fread(header, 1, 12, file) != 12 || memcmp(header, "RIFF", 4) || memcmp(header + 8, "WAVE", 4)) goto fail;
    while (fread(chunk, 1, 8, file) == 8) {
        unsigned int size = le32(chunk + 4);
        if (!memcmp(chunk, "fmt ", 4)) {
            if (size < 16 || fread(format, 1, 16, file) != 16 || le16(format) != 1) goto fail;
            channels = le16(format + 2); rate = le32(format + 4); bits = le16(format + 14);
            if (fseek(file, (long)(size - 16 + (size & 1U)), SEEK_CUR)) goto fail;
        } else if (!memcmp(chunk, "data", 4)) { offset = ftell(file); data_size = size; break; }
        else if (fseek(file, (long)(size + (size & 1U)), SEEK_CUR)) goto fail;
    }
    if (!channels || !rate || bits != 16 || !data_size || offset <= 0) goto fail;
    data = malloc(data_size);
    if (!data || fseek(file, offset, SEEK_SET) || fread(data, 1, data_size, file) != data_size) goto fail;
    size_t frame_bytes = channels * 2U, frames = data_size / frame_bytes;
    size_t per = (size_t)(rate * ENVELOPE_HOP); if (!per) per = 1;
    *count = (frames + per - 1) / per;
    result = calloc(*count, 1); if (!result) goto fail;
    double maximum = 1.0;
    for (size_t pass = 0; pass < 2; pass++) for (size_t block = 0; block < *count; block++) {
        size_t begin = block * per, end = begin + per < frames ? begin + per : frames, samples = 0;
        double sum = 0.0;
        for (size_t frame = begin; frame < end; frame++) for (unsigned int channel = 0; channel < channels; channel++) {
            int sample = (short)le16(data + frame * frame_bytes + channel * 2U);
            sum += (double)sample * sample; samples++;
        }
        double rms = samples ? sqrt(sum / samples) : 0.0;
        if (pass == 0 && rms > maximum) maximum = rms;
        if (pass == 1) result[block] = (unsigned char)(20.0 + rms / maximum * 235.0);
    }
    fclose(file); free(data); *levels = result; return 0;
fail:
    if (file) fclose(file);
    free(data);
    free(result);
    return -1;
}

int voice_stage_envelope(const char *input_path, const char *output_path)
{
    unsigned char *levels = NULL;
    size_t count = 0;
    FILE *output;
    if (wav_levels(input_path, &levels, &count) != 0 || count > UINT32_MAX) return -1;
    output = fopen(output_path, "wb");
    if (!output) { free(levels); return -1; }
    unsigned char value[4] = {
        (unsigned char)count, (unsigned char)(count >> 8),
        (unsigned char)(count >> 16), (unsigned char)(count >> 24)
    };
    int failed = fwrite("RVL1", 1, 4, output) != 4 || fwrite(value, 1, 4, output) != 4 ||
                 fwrite(levels, 1, count, output) != count || fclose(output) != 0;
    free(levels);
    return failed ? -1 : 0;
}

int voice_envelope_load(const char *path, unsigned char **levels, size_t *count, double *hop)
{
    FILE *input = fopen(path, "rb");
    char magic[4]; unsigned char encoded[4]; unsigned int value;
    if (!input || fread(magic, 1, 4, input) != 4 || memcmp(magic, "RVL1", 4) ||
        fread(encoded, 1, 4, input) != 4) { if (input) fclose(input); return -1; }
    value = le32(encoded);
    if (value > 1000000) { fclose(input); return -1; }
    unsigned char *data = malloc(value ? value : 1);
    if (!data || fread(data, 1, value, input) != value) { free(data); fclose(input); return -1; }
    fclose(input); *levels = data; *count = value; *hop = ENVELOPE_HOP; return 0;
}
