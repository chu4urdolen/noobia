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
#include "voice_remote.h"
#include "voice_stage.h"

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

static int temporary_path(char *path, size_t size, const char *kind, const char *suffix)
{
    int result = snprintf(path, size, "/tmp/rose-voice-%s-XXXXXX%s", kind, suffix);
    int descriptor;

    if (result < 0 || (size_t)result >= size) return -1;
    descriptor = mkstemps(path, (int)strlen(suffix));
    if (descriptor < 0) return -1;
    close(descriptor);
    return 0;
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

static int play_sentence(char *const play_argv[], const char *envelope_path,
                         const struct hue_config *hue, bool lights_enabled)
{
    unsigned char *levels = NULL;
    size_t level_count = 0;
    double hop = 0.125;
    unsigned int red, green, blue;
    char error[256];
    pid_t player;

    if (!lights_enabled || voice_envelope_load(envelope_path, &levels, &level_count, &hop) != 0)
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
        long hop_ns = (long)(hop * 1000000000.0);
        next.tv_nsec += hop_ns;
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
    char text_path[PATH_MAX];
    char dry_path[PATH_MAX];
    char wet_path[PATH_MAX];
    char envelope_path[PATH_MAX];
    bool dry_ready;
    bool wet_ready;
    bool envelope_ready;
};

struct pipeline {
    struct audio_item *items;
    size_t count;
    const contact *piper_worker;
    const contact *sox_worker;
    const contact *envelope_worker;
    const char *local_name;
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
        int stage_result = pipeline->piper_worker != NULL ?
            voice_remote_run(pipeline->piper_worker, pipeline->local_name, VOICE_TASK_PIPER,
                             pipeline->items[i].text_path, pipeline->items[i].dry_path) : -1;
        if (stage_result != 0)
            stage_result = voice_stage_piper(pipeline->items[i].text_path,
                                             pipeline->items[i].dry_path);
        if (stage_result != 0) {
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
        pthread_mutex_lock(&pipeline->mutex);
        while (!pipeline->items[i].dry_ready && !pipeline->failed)
            pthread_cond_wait(&pipeline->changed, &pipeline->mutex);
        bool failed = pipeline->failed;
        pthread_mutex_unlock(&pipeline->mutex);
        if (failed) break;
        int stage_result = pipeline->sox_worker != NULL ?
            voice_remote_run(pipeline->sox_worker, pipeline->local_name, VOICE_TASK_SOX,
                             pipeline->items[i].dry_path, pipeline->items[i].wet_path) : -1;
        if (stage_result != 0)
            stage_result = voice_stage_sox(pipeline->items[i].dry_path,
                                           pipeline->items[i].wet_path);
        if (stage_result != 0) {
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

static void *envelope_worker(void *argument)
{
    struct pipeline *pipeline = argument;
    for (size_t i = 0; i < pipeline->count; i++) {
        pthread_mutex_lock(&pipeline->mutex);
        while (!pipeline->items[i].dry_ready && !pipeline->failed)
            pthread_cond_wait(&pipeline->changed, &pipeline->mutex);
        bool failed = pipeline->failed;
        pthread_mutex_unlock(&pipeline->mutex);
        if (failed) break;
        int stage_result = pipeline->envelope_worker != NULL ?
            voice_remote_run(pipeline->envelope_worker, pipeline->local_name,
                             VOICE_TASK_ENVELOPE, pipeline->items[i].dry_path,
                             pipeline->items[i].envelope_path) : -1;
        if (stage_result != 0)
            stage_result = voice_stage_envelope(pipeline->items[i].dry_path,
                                                pipeline->items[i].envelope_path);
        if (stage_result != 0) { pipeline_fail(pipeline); break; }
        pthread_mutex_lock(&pipeline->mutex);
        pipeline->items[i].envelope_ready = true;
        pthread_cond_broadcast(&pipeline->changed);
        pthread_mutex_unlock(&pipeline->mutex);
    }
    return NULL;
}

static const contact *preferred_worker(const contact_book *contacts, const char *name,
                                       const char *local_name)
{
    const contact *worker = contact_book_find(contacts, name);
    if (worker == NULL || worker->role != CONTACT_AI || !strcmp(worker->name, local_name))
        return NULL;
    return voice_remote_available(worker, local_name) ? worker : NULL;
}

int main(int argc, char **argv)
{
    const char *sink = env_or_default("ROSE_AUDIO_SINK", DEFAULT_SINK);
    const char *local_name = env_or_default("ROSE_NAME", "Rose");
    const char *contacts_path = env_or_default("ROSE_CONTACTS_FILE",
                                               "/etc/noobia-council/contacts.json");
    char *text;
    char **sentences = NULL;
    size_t sentence_count = 0;
    struct pipeline pipeline = {0};
    pthread_t piper_thread, sox_thread, envelope_thread;
    bool piper_started = false, sox_started = false, envelope_started = false;
    contact_book contacts;
    char contact_error[256];
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
    srand((unsigned int)(time(NULL) ^ getpid()));
    sentences = split_sentences(text, &sentence_count);
    if (sentences == NULL || sentence_count == 0) goto cleanup;
    pipeline.items = calloc(sentence_count, sizeof(*pipeline.items));
    if (pipeline.items == NULL) goto cleanup;
    pipeline.count = sentence_count;
    pipeline.local_name = local_name;
    if (contact_book_load(contacts_path, &contacts, contact_error, sizeof(contact_error)) == 0) {
        pipeline.piper_worker = preferred_worker(&contacts, "Aria", local_name);
        pipeline.sox_worker = preferred_worker(&contacts, "Rose", local_name);
        pipeline.envelope_worker = preferred_worker(&contacts, "Argus", local_name);
    } else {
        fprintf(stderr, "distributed workers unavailable: %s\n", contact_error);
    }
    fprintf(stderr, "voice stages piper=%s sox=%s envelope=%s\n",
            pipeline.piper_worker ? pipeline.piper_worker->name : local_name,
            pipeline.sox_worker ? pipeline.sox_worker->name : local_name,
            pipeline.envelope_worker ? pipeline.envelope_worker->name : local_name);
    if (pthread_mutex_init(&pipeline.mutex, NULL) != 0 ||
        pthread_cond_init(&pipeline.changed, NULL) != 0) goto cleanup;
    for (size_t i = 0; i < sentence_count; i++) {
        pipeline.items[i].text = sentences[i];
        if (temporary_path(pipeline.items[i].text_path, PATH_MAX, "text", ".txt") != 0 ||
            temporary_path(pipeline.items[i].dry_path, PATH_MAX, "dry", ".wav") != 0 ||
            temporary_path(pipeline.items[i].wet_path, PATH_MAX, "fx", ".wav") != 0 ||
            temporary_path(pipeline.items[i].envelope_path, PATH_MAX, "light", ".env") != 0) {
            perror("temporary file");
            goto pipeline_cleanup;
        }
        FILE *sentence_file = fopen(pipeline.items[i].text_path, "wb");
        size_t text_length = strlen(sentences[i]);
        if (sentence_file == NULL) goto pipeline_cleanup;
        if (fwrite(sentences[i], 1, text_length, sentence_file) != text_length) {
            fclose(sentence_file);
            goto pipeline_cleanup;
        }
        if (fclose(sentence_file) != 0) goto pipeline_cleanup;
    }
    if (pthread_create(&piper_thread, NULL, piper_worker, &pipeline) != 0) goto pipeline_cleanup;
    piper_started = true;
    if (pthread_create(&sox_thread, NULL, sox_worker, &pipeline) != 0) {
        pipeline_fail(&pipeline);
        goto pipeline_cleanup;
    }
    sox_started = true;
    if (pthread_create(&envelope_thread, NULL, envelope_worker, &pipeline) != 0) {
        pipeline_fail(&pipeline);
        goto pipeline_cleanup;
    }
    envelope_started = true;
    for (size_t index = 0; index < sentence_count; index++) {
        pthread_mutex_lock(&pipeline.mutex);
        while ((!pipeline.items[index].wet_ready || !pipeline.items[index].envelope_ready) &&
               !pipeline.failed)
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
        if (play_sentence(play_argv, pipeline.items[index].envelope_path, &hue,
                          lights_enabled) != 0) {
            pipeline_fail(&pipeline);
            goto pipeline_cleanup;
        }
        unlink(pipeline.items[index].wet_path);
        pipeline.items[index].wet_path[0] = '\0';
        unlink(pipeline.items[index].dry_path);
        pipeline.items[index].dry_path[0] = '\0';
        unlink(pipeline.items[index].text_path);
        pipeline.items[index].text_path[0] = '\0';
        unlink(pipeline.items[index].envelope_path);
        pipeline.items[index].envelope_path[0] = '\0';
    }
    result = EXIT_SUCCESS;

pipeline_cleanup:
    if (result != EXIT_SUCCESS) pipeline_fail(&pipeline);
    if (piper_started) pthread_join(piper_thread, NULL);
    if (sox_started) pthread_join(sox_thread, NULL);
    if (envelope_started) pthread_join(envelope_thread, NULL);

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
            if (*pipeline.items[i].text_path != '\0') unlink(pipeline.items[i].text_path);
            if (*pipeline.items[i].envelope_path != '\0') unlink(pipeline.items[i].envelope_path);
        }
    }
    free(pipeline.items);
    free(sentences);
    free(text);
    return result;
}
