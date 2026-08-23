#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <math.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#include "hue_client.h"

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

static unsigned int read_u16_le(const unsigned char *p)
{
    return (unsigned int)p[0] | ((unsigned int)p[1] << 8);
}

static unsigned int read_u32_le(const unsigned char *p)
{
    return (unsigned int)p[0] | ((unsigned int)p[1] << 8) |
           ((unsigned int)p[2] << 16) | ((unsigned int)p[3] << 24);
}

static int load_envelope(const char *path, unsigned char **levels, size_t *level_count,
                         double hop_seconds)
{
    FILE *file = fopen(path, "rb");
    unsigned char header[12], chunk[8], format[16];
    unsigned int channels = 0, rate = 0, bits = 0, data_size = 0;
    long data_offset = 0;
    unsigned char *data = NULL, *output = NULL;
    if (file == NULL || fread(header, 1, sizeof(header), file) != sizeof(header) ||
        memcmp(header, "RIFF", 4) != 0 || memcmp(header + 8, "WAVE", 4) != 0) goto fail;
    while (fread(chunk, 1, sizeof(chunk), file) == sizeof(chunk)) {
        unsigned int size = read_u32_le(chunk + 4);
        if (memcmp(chunk, "fmt ", 4) == 0) {
            if (size < 16 || fread(format, 1, sizeof(format), file) != sizeof(format)) goto fail;
            if (read_u16_le(format) != 1) goto fail;
            channels = read_u16_le(format + 2);
            rate = read_u32_le(format + 4);
            bits = read_u16_le(format + 14);
            if (fseek(file, (long)(size - 16 + (size & 1U)), SEEK_CUR) != 0) goto fail;
        } else if (memcmp(chunk, "data", 4) == 0) {
            data_offset = ftell(file);
            data_size = size;
            break;
        } else if (fseek(file, (long)(size + (size & 1U)), SEEK_CUR) != 0) goto fail;
    }
    if (channels == 0 || rate == 0 || bits != 16 || data_size < 2 || data_offset <= 0) goto fail;
    data = malloc(data_size);
    if (data == NULL || fseek(file, data_offset, SEEK_SET) != 0 ||
        fread(data, 1, data_size, file) != data_size) goto fail;
    size_t frame_bytes = channels * 2U;
    size_t frames = data_size / frame_bytes;
    size_t frames_per_hop = (size_t)(rate * hop_seconds);
    if (frames_per_hop == 0) frames_per_hop = 1;
    *level_count = (frames + frames_per_hop - 1) / frames_per_hop;
    output = calloc(*level_count, 1);
    if (output == NULL) goto fail;
    double maximum = 1.0;
    for (size_t block = 0; block < *level_count; block++) {
        size_t start = block * frames_per_hop;
        size_t end = start + frames_per_hop < frames ? start + frames_per_hop : frames;
        double sum = 0.0;
        size_t samples = 0;
        for (size_t frame = start; frame < end; frame++) {
            for (unsigned int channel = 0; channel < channels; channel++) {
                const unsigned char *p = data + frame * frame_bytes + channel * 2U;
                int sample = (int)(short)read_u16_le(p);
                sum += (double)sample * sample;
                samples++;
            }
        }
        double rms = samples == 0 ? 0.0 : sqrt(sum / samples);
        if (rms > maximum) maximum = rms;
    }
    for (size_t block = 0; block < *level_count; block++) {
        size_t start = block * frames_per_hop;
        size_t end = start + frames_per_hop < frames ? start + frames_per_hop : frames;
        double sum = 0.0;
        size_t samples = 0;
        for (size_t frame = start; frame < end; frame++) {
            for (unsigned int channel = 0; channel < channels; channel++) {
                const unsigned char *p = data + frame * frame_bytes + channel * 2U;
                int sample = (int)(short)read_u16_le(p);
                sum += (double)sample * sample;
                samples++;
            }
        }
        double normalized = samples == 0 ? 0.0 : sqrt(sum / samples) / maximum;
        output[block] = (unsigned char)(20.0 + normalized * 235.0);
    }
    fclose(file);
    free(data);
    *levels = output;
    return 0;
fail:
    if (file != NULL) fclose(file);
    free(data);
    free(output);
    return -1;
}

static void parse_hue_color(unsigned int *red, unsigned int *green, unsigned int *blue)
{
    const char *value = env_or_default("ROSE_HUE_COLOR", "40,255,100");
    unsigned int r, g, b;
    if (sscanf(value, "%u,%u,%u", &r, &g, &b) == 3 && r <= 255 && g <= 255 && b <= 255) {
        *red = r; *green = g; *blue = b;
    } else {
        *red = 40; *green = 255; *blue = 100;
    }
}

static int play_sentence(char *const play_argv[], const char *dry_path,
                         const struct hue_config *hue, bool lights_enabled)
{
    unsigned char *levels = NULL;
    size_t level_count = 0;
    const double hop = 0.125;
    unsigned int red, green, blue;
    char error[256];
    pid_t player;

    if (!lights_enabled || load_envelope(dry_path, &levels, &level_count, hop) != 0)
        return run_command(play_argv);
    parse_hue_color(&red, &green, &blue);
    player = fork();
    if (player < 0) { free(levels); return -1; }
    if (player == 0) { execvp(play_argv[0], play_argv); _exit(127); }
    struct timespec next;
    clock_gettime(CLOCK_MONOTONIC, &next);
    for (size_t i = 0; i < level_count; i++) {
        if (hue_set_rgb(hue, red, green, blue, levels[i], 0.1, error, sizeof(error)) != 0) {
            fprintf(stderr, "Hue animation disabled: %s\n", error);
            break;
        }
        next.tv_nsec += 125000000L;
        if (next.tv_nsec >= 1000000000L) { next.tv_sec++; next.tv_nsec -= 1000000000L; }
        while (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next, NULL) == EINTR) {}
    }
    free(levels);
    return wait_for_child(player, play_argv[0]);
}

static char **split_sentences(char *text, size_t *count)
{
    size_t capacity = 8;
    char **sentences = malloc(capacity * sizeof(*sentences));
    char *start = text;
    if (sentences == NULL) return NULL;
    *count = 0;
    while (*start != '\0') {
        while (*start == ' ' || *start == '\t' || *start == '\r' || *start == '\n') start++;
        if (*start == '\0') break;
        if (*count == capacity) {
            capacity *= 2;
            char **larger = realloc(sentences, capacity * sizeof(*sentences));
            if (larger == NULL) { free(sentences); return NULL; }
            sentences = larger;
        }
        sentences[(*count)++] = start;
        while (*start != '\0') {
            if ((*start == '.' || *start == '?' || *start == '!') &&
                (start[1] == '\0' || start[1] == ' ' || start[1] == '\t' ||
                 start[1] == '\r' || start[1] == '\n')) {
                start++;
                while (*start == ' ' || *start == '\t' || *start == '\r' || *start == '\n')
                    *start++ = '\0';
                break;
            }
            start++;
        }
    }
    return sentences;
}

struct audio_item {
    char *text;
    char dry_path[PATH_MAX];
    char wet_path[PATH_MAX];
    bool dry_ready;
    bool wet_ready;
};

struct pipeline {
    struct audio_item *items;
    size_t count;
    const char *piper;
    const char *voice;
    const char *sox;
    pthread_mutex_t mutex;
    pthread_cond_t changed;
    bool failed;
};

static void pipeline_fail(struct pipeline *pipeline)
{
    pthread_mutex_lock(&pipeline->mutex);
    pipeline->failed = true;
    pthread_cond_broadcast(&pipeline->changed);
    pthread_mutex_unlock(&pipeline->mutex);
}

static void *piper_worker(void *argument)
{
    struct pipeline *pipeline = argument;
    for (size_t i = 0; i < pipeline->count; i++) {
        pthread_mutex_lock(&pipeline->mutex);
        bool failed = pipeline->failed;
        pthread_mutex_unlock(&pipeline->mutex);
        if (failed) break;
        char *argv[] = {(char *)pipeline->piper, "--model", (char *)pipeline->voice,
                        "--output_file", pipeline->items[i].dry_path, NULL};
        if (run_with_input(argv, pipeline->items[i].text) != 0) {
            pipeline_fail(pipeline);
            break;
        }
        pthread_mutex_lock(&pipeline->mutex);
        pipeline->items[i].dry_ready = true;
        pthread_cond_broadcast(&pipeline->changed);
        pthread_mutex_unlock(&pipeline->mutex);
    }
    return NULL;
}

static void *sox_worker(void *argument)
{
    struct pipeline *pipeline = argument;
    for (size_t i = 0; i < pipeline->count; i++) {
        char pitch[16];
        pthread_mutex_lock(&pipeline->mutex);
        while (!pipeline->items[i].dry_ready && !pipeline->failed)
            pthread_cond_wait(&pipeline->changed, &pipeline->mutex);
        bool failed = pipeline->failed;
        pthread_mutex_unlock(&pipeline->mutex);
        if (failed) break;
        snprintf(pitch, sizeof(pitch), "%d", -(10 + rand() % 151));
        char *argv[] = {
            (char *)pipeline->sox, pipeline->items[i].dry_path, pipeline->items[i].wet_path,
            "gain", "-3", "pitch", pitch,
            "chorus", "0.5", "0.9", "50", "0.4", "0.25", "2", "-t",
            "60", "0.32", "0.4", "2.3", "-t",
            "40", "0.3", "0.3", "1.3", "-s",
            "reverse", "reverb", "80", "50", "100", "100", "25", "-1",
            "reverse", NULL
        };
        if (run_command(argv) != 0) {
            pipeline_fail(pipeline);
            break;
        }
        pthread_mutex_lock(&pipeline->mutex);
        pipeline->items[i].wet_ready = true;
        pthread_cond_broadcast(&pipeline->changed);
        pthread_mutex_unlock(&pipeline->mutex);
    }
    return NULL;
}

int main(int argc, char **argv)
{
    const char *piper = env_or_default("ROSE_PIPER_BIN", DEFAULT_PIPER);
    const char *voice = env_or_default("ROSE_PIPER_VOICE", DEFAULT_VOICE);
    const char *sox = env_or_default("ROSE_SOX_BIN", "sox");
    const char *sink = env_or_default("ROSE_AUDIO_SINK", DEFAULT_SINK);
    char *text;
    char **sentences = NULL;
    size_t sentence_count = 0;
    struct pipeline pipeline = {0};
    pthread_t piper_thread, sox_thread;
    bool piper_started = false, sox_started = false;
    struct hue_config hue;
    bool lights_enabled = false;
    bool lock_held = false;
    char hue_error[256];
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
    srand((unsigned int)(time(NULL) ^ getpid()));
    sentences = split_sentences(text, &sentence_count);
    if (sentences == NULL || sentence_count == 0) goto cleanup;
    pipeline.items = calloc(sentence_count, sizeof(*pipeline.items));
    if (pipeline.items == NULL) goto cleanup;
    pipeline.count = sentence_count;
    pipeline.piper = piper;
    pipeline.voice = voice;
    pipeline.sox = sox;
    if (pthread_mutex_init(&pipeline.mutex, NULL) != 0 ||
        pthread_cond_init(&pipeline.changed, NULL) != 0) goto cleanup;
    for (size_t i = 0; i < sentence_count; i++) {
        pipeline.items[i].text = sentences[i];
        if (temporary_wav(pipeline.items[i].dry_path, PATH_MAX, "dry") != 0 ||
            temporary_wav(pipeline.items[i].wet_path, PATH_MAX, "fx") != 0) {
            perror("temporary file");
            goto pipeline_cleanup;
        }
    }
    if (pthread_create(&piper_thread, NULL, piper_worker, &pipeline) != 0) goto pipeline_cleanup;
    piper_started = true;
    if (pthread_create(&sox_thread, NULL, sox_worker, &pipeline) != 0) {
        pipeline_fail(&pipeline);
        goto pipeline_cleanup;
    }
    sox_started = true;
    for (size_t index = 0; index < sentence_count; index++) {
        pthread_mutex_lock(&pipeline.mutex);
        while (!pipeline.items[index].wet_ready && !pipeline.failed)
            pthread_cond_wait(&pipeline.changed, &pipeline.mutex);
        bool failed = pipeline.failed;
        pthread_mutex_unlock(&pipeline.mutex);
        if (failed) goto pipeline_cleanup;
        if (index == 0 && strcmp(env_or_default("ROSE_HUE_ENABLED", "0"), "0") != 0 &&
            hue_config_load(&hue) == 0) {
            if (hue_lock_acquire(30, hue_error, sizeof(hue_error)) == 0) {
                lights_enabled = true;
                lock_held = true;
            } else {
                fprintf(stderr, "Hue animation disabled: %s\n", hue_error);
            }
        }
        char *play_argv[] = {"pw-play", "--target", (char *)sink,
                             pipeline.items[index].wet_path, NULL};
        if (play_sentence(play_argv, pipeline.items[index].dry_path, &hue,
                          lights_enabled) != 0) {
            pipeline_fail(&pipeline);
            goto pipeline_cleanup;
        }
        unlink(pipeline.items[index].wet_path);
        pipeline.items[index].wet_path[0] = '\0';
        unlink(pipeline.items[index].dry_path);
        pipeline.items[index].dry_path[0] = '\0';
    }
    result = EXIT_SUCCESS;

pipeline_cleanup:
    if (result != EXIT_SUCCESS) pipeline_fail(&pipeline);
    if (piper_started) pthread_join(piper_thread, NULL);
    if (sox_started) pthread_join(sox_thread, NULL);

cleanup:
    if (lock_held) {
        if (hue_dark(&hue, hue_error, sizeof(hue_error)) != 0)
            fprintf(stderr, "could not darken Hue target: %s\n", hue_error);
        hue_lock_release();
    }
    if (pipeline.items != NULL) {
        for (size_t i = 0; i < pipeline.count; i++) {
            if (*pipeline.items[i].wet_path != '\0') unlink(pipeline.items[i].wet_path);
            if (*pipeline.items[i].dry_path != '\0') unlink(pipeline.items[i].dry_path);
        }
    }
    free(pipeline.items);
    free(sentences);
    free(text);
    return result;
}
