#define _POSIX_C_SOURCE 200809L

#include "hue_client.h"

#include <ctype.h>
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <stdbool.h>
#include <signal.h>

static volatile sig_atomic_t interrupted = 0;

static void stop_pattern(int signal_number)
{
    (void)signal_number;
    interrupted = 1;
}

static char *trim(char *text)
{
    char *end;
    while (isspace((unsigned char)*text)) text++;
    end = text + strlen(text);
    while (end > text && isspace((unsigned char)end[-1])) end--;
    *end = '\0';
    return text;
}

static int sleep_seconds(double seconds)
{
    struct timespec remaining = {(time_t)seconds, (long)((seconds - (time_t)seconds) * 1e9)};
    while (nanosleep(&remaining, &remaining) != 0) {
        if (interrupted) return 0;
        if (errno != EINTR) return -1;
    }
    return 0;
}

static int parse_row(char *line, unsigned int values[4], double *duration)
{
    char *cursor = line;
    for (size_t field = 0; field < 5; field++) {
        char *end;
        double number;
        cursor = trim(cursor);
        errno = 0;
        number = strtod(cursor, &end);
        if (errno != 0 || end == cursor || !isfinite(number)) return -1;
        end = trim(end);
        if (field < 4) {
            if (number < 0.0 || number > 255.0 || number != (unsigned int)number) return -1;
            values[field] = (unsigned int)number;
        } else {
            if (number < 0.0 || number > 3600.0) return -1;
            *duration = number;
        }
        if (field < 4) {
            if (*end != ',') return -1;
            cursor = end + 1;
        } else if (*end != '\0' && *end != '#') return -1;
    }
    return 0;
}

int main(int argc, char **argv)
{
    struct hue_config config;
    char line[2048], error[256];
    const char *csv_path = NULL;
    FILE *csv;
    unsigned long line_number = 0, applied = 0;
    bool dry_run = false;
    bool header_seen = false;
    bool locked = false;
    int result = EXIT_FAILURE;

    if (hue_config_load(&config) != 0) {
        fprintf(stderr, "Hue is not configured; see hue.conf.example\n");
        return EXIT_FAILURE;
    }
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--dry-run") == 0) {
            dry_run = true;
        } else if (strcmp(argv[i], "--light") == 0 && i + 1 < argc) {
            snprintf(config.target, sizeof(config.target), "lights/%s/state", argv[++i]);
        } else if (strcmp(argv[i], "--group") == 0 && i + 1 < argc) {
            snprintf(config.target, sizeof(config.target), "groups/%s/action", argv[++i]);
        } else if (csv_path == NULL) {
            csv_path = argv[i];
        } else {
            fprintf(stderr, "Usage: %s [--dry-run] [--light ID|--group ID] PATTERN.csv\n", argv[0]);
            return EXIT_FAILURE;
        }
    }
    if (csv_path == NULL) {
        fprintf(stderr, "Usage: %s [--dry-run] [--light ID|--group ID] PATTERN.csv\n", argv[0]);
        return EXIT_FAILURE;
    }
    signal(SIGINT, stop_pattern);
    signal(SIGTERM, stop_pattern);
    if (!dry_run) {
        if (hue_lock_acquire(30, error, sizeof(error)) != 0) {
            fprintf(stderr, "%s\n", error);
            return EXIT_FAILURE;
        }
        locked = true;
    }
    csv = strcmp(csv_path, "-") == 0 ? stdin : fopen(csv_path, "r");
    if (csv == NULL) {
        perror(csv_path);
        goto cleanup;
    }
    while (fgets(line, sizeof(line), csv) != NULL) {
        unsigned int values[4];
        double duration;
        char *content = trim(line);
        line_number++;
        if (*content == '\0' || *content == '#') continue;
        if (parse_row(content, values, &duration) != 0) {
            if (applied == 0 && !header_seen && isalpha((unsigned char)*content)) {
                header_seen = true;
                continue;
            }
            fprintf(stderr, "%s:%lu: expected red,green,blue,brightness,time\n", csv_path, line_number);
            if (csv != stdin) fclose(csv);
            goto cleanup;
        }
        if (!dry_run && hue_set_rgb(&config, values[0], values[1], values[2], values[3],
                                    duration, error, sizeof(error)) != 0) {
            fprintf(stderr, "%s:%lu: %s\n", csv_path, line_number, error);
            if (csv != stdin) fclose(csv);
            goto cleanup;
        }
        applied++;
        if (!dry_run && sleep_seconds(duration) != 0) break;
        if (interrupted) break;
    }
    if (csv != stdin) fclose(csv);
    if (applied == 0) {
        fprintf(stderr, "%s: no pattern rows found\n", csv_path);
        goto cleanup;
    }
    result = interrupted ? EXIT_FAILURE : EXIT_SUCCESS;
cleanup:
    if (locked) {
        if (hue_dark(&config, error, sizeof(error)) != 0)
            fprintf(stderr, "could not darken Hue target: %s\n", error);
        hue_lock_release();
    }
    return result;
}
