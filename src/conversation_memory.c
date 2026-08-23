#define _POSIX_C_SOURCE 200809L
#include "conversation_summary.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define RECENT_LINES 20
#define LOG_LINE_SIZE 8192
int conversation_summary_rebuild(const char *log_path, const char *summary_path) {
    FILE *input, *output;
    char line[LOG_LINE_SIZE], temporary[1024];
    char *recent[RECENT_LINES] = {0};
    size_t events = 0, messages = 0, decisions = 0, index = 0, count = 0, i;
    if (!summary_path || !summary_path[0]) return 0;
    input = fopen(log_path, "r");
    snprintf(temporary, sizeof(temporary), "%s.new", summary_path);
    output = fopen(temporary, "w");
    if (!output) { if (input) fclose(input); return -1; }
    if (input) {
        while (fgets(line, sizeof(line), input)) {
            char *copy;
            events++;
            if (strstr(line, "\tmessage\t") || strstr(line, "\tinitiate\t")) messages++;
            if (strstr(line, "\tgrant\t") || strstr(line, "\tspeak\t")) decisions++;
            copy = malloc(strlen(line) + 1);
            if (!copy) continue;
            strcpy(copy, line);
            free(recent[index]); recent[index] = copy;
            index = (index + 1) % RECENT_LINES;
            if (count < RECENT_LINES) count++;
        }
        fclose(input);
    }
    fprintf(output, "Council memory\nEvents: %lu; messages: %lu; speaking decisions: %lu.\nRecent context:\n", (unsigned long)events, (unsigned long)messages, (unsigned long)decisions);
    for (i = 0; i < count; i++) {
        size_t position = (index + RECENT_LINES - count + i) % RECENT_LINES;
        fputs(recent[position], output); free(recent[position]);
    }
    if (fclose(output)) return -1;
#ifdef _WIN32
    remove(summary_path);
#endif
    return rename(temporary, summary_path);
}
