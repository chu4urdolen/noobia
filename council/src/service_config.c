#include "service_config.h"
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void trim(char *text) {
    char *start = text;
    char *end;
    while (isspace((unsigned char)*start)) start++;
    if (start != text) memmove(text, start, strlen(start) + 1);
    end = text + strlen(text);
    while (end > text && isspace((unsigned char)end[-1])) *--end = 0;
}
static int copy_text(char *to, size_t size, const char *from) {
    if (strlen(from) >= size) return -1;
    memcpy(to, from, strlen(from) + 1);
    return 0;
}
int service_config_load(const char *path, service_config *c, char *error, size_t error_size) {
    FILE *file;
    char line[1024];
    int line_number = 0;
    memset(c, 0, sizeof(*c));
    copy_text(c->bind_address, sizeof(c->bind_address), "0.0.0.0");
    c->presence_seconds = 15;
    c->max_file_bytes = 10U * 1024U * 1024U;
    file = fopen(path, "r");
    if (!file) { snprintf(error, error_size, "cannot open %s", path); return -1; }
    while (fgets(line, sizeof(line), file)) {
        char *equals;
        char *key;
        char *value;
        line_number++;
        trim(line);
        if (!line[0] || line[0] == '#' || line[0] == '[') continue;
        equals = strchr(line, '=');
        if (!equals) goto invalid;
        *equals = 0; key = line; value = equals + 1; trim(key); trim(value);
        if (!strcmp(key, "name")) copy_text(c->name, sizeof(c->name), value);
        else if (!strcmp(key, "role")) c->role = !strcmp(value, "human") ? CONTACT_HUMAN : CONTACT_AI;
        else if (!strcmp(key, "bind_address")) copy_text(c->bind_address, sizeof(c->bind_address), value);
        else if (!strcmp(key, "human_port")) c->human_port = (uint16_t)atoi(value);
        else if (!strcmp(key, "ai_port")) c->ai_port = (uint16_t)atoi(value);
        else if (!strcmp(key, "is_hub")) c->is_hub = !strcmp(value, "true") || !strcmp(value, "1");
        else if (!strcmp(key, "hub_host")) copy_text(c->hub_host, sizeof(c->hub_host), value);
        else if (!strcmp(key, "hub_port")) c->hub_port = (uint16_t)atoi(value);
        else if (!strcmp(key, "own_key")) copy_text(c->own_key, sizeof(c->own_key), value);
        else if (!strcmp(key, "contacts_file")) copy_text(c->contacts_path, sizeof(c->contacts_path), value);
        else if (!strcmp(key, "transcript_file")) copy_text(c->transcript_path, sizeof(c->transcript_path), value);
        else if (!strcmp(key, "inbox_file")) copy_text(c->inbox_path, sizeof(c->inbox_path), value);
        else if (!strcmp(key, "summary_file")) copy_text(c->summary_path, sizeof(c->summary_path), value);
        else if (!strcmp(key, "activity_file")) copy_text(c->activity_path, sizeof(c->activity_path), value);
        else if (!strcmp(key, "files_directory")) copy_text(c->files_directory, sizeof(c->files_directory), value);
        else if (!strcmp(key, "max_file_bytes")) c->max_file_bytes = (uint64_t)strtoull(value, NULL, 10);
        else if (!strcmp(key, "presence_seconds")) c->presence_seconds = atoi(value);
        else if (!strcmp(key, "os_user") || !strcmp(key, "bridge_host") ||
                 !strcmp(key, "bridge_port") || !strcmp(key, "bridge_key_file") ||
                 !strcmp(key, "bridge_state_dir") || !strcmp(key, "work_directory") ||
                 !strcmp(key, "web_bind") || !strcmp(key, "web_port") ||
                 !strcmp(key, "web_identity") || !strcmp(key, "web_hub_host") ||
                 !strcmp(key, "web_hub_port") || !strcmp(key, "web_key_file") ||
                 !strcmp(key, "web_password_file") || !strcmp(key, "desired_ip") ||
                 !strcmp(key, "mac")) { /* consumed by systemd or the installer */ }
        else goto invalid;
    }
    fclose(file);
    if (!c->name[0] || !c->human_port || !c->ai_port || !c->contacts_path[0]) {
        snprintf(error, error_size, "name, human_port, ai_port, and contacts_file are required");
        return -1;
    }
    return 0;
invalid:
    fclose(file); snprintf(error, error_size, "invalid setting at line %d", line_number); return -1;
}
