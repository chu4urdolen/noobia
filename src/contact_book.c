#include "contact_book.h"
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char *read_file(const char *path, char *error, size_t error_size) {
    FILE *file = fopen(path, "rb"); long size; char *text;
    if (!file) { snprintf(error, error_size, "cannot open %s", path); return NULL; }
    if (fseek(file, 0, SEEK_END) || (size = ftell(file)) < 0 || fseek(file, 0, SEEK_SET)) { fclose(file); return NULL; }
    text = malloc((size_t)size + 1);
    if (!text || fread(text, 1, (size_t)size, file) != (size_t)size) { free(text); fclose(file); return NULL; }
    text[size] = 0; fclose(file); return text;
}
static const char *skip_space(const char *p) { while (isspace((unsigned char)*p)) p++; return p; }
static int copy_value(char *output, size_t size, const char *value) {
    size_t length = strlen(value);
    if (length >= size) return -1;
    memcpy(output, value, length + 1);
    return 0;
}
static int json_string(const char **cursor, char *out, size_t size) {
    const char *p = skip_space(*cursor); size_t used = 0;
    if (*p++ != '"') return -1;
    while (*p && *p != '"') {
        char value = *p++;
        if (value == '\\') { value = *p++; if (value != '\\' && value != '"' && value != '/') return -1; }
        if ((unsigned char)value < 32 || used + 1 >= size) return -1;
        out[used++] = value;
    }
    if (*p++ != '"') return -1;
    out[used] = 0; *cursor = p; return 0;
}
static int expect(const char **cursor, char token) { const char *p = skip_space(*cursor); if (*p != token) return -1; *cursor = p + 1; return 0; }
int contact_book_load(const char *path, contact_book *book, char *error, size_t error_size) {
    char *text = read_file(path, error, error_size); const char *p;
    if (!text) return -1;
    memset(book, 0, sizeof(*book));
    p = text;
    if (expect(&p, '[')) goto invalid;
    while (*skip_space(p) != ']') {
        contact item; int fields = 0; memset(&item, 0, sizeof(item));
        if (book->count == COUNCIL_MAX_CONTACTS || expect(&p, '{')) goto invalid;
        while (*skip_space(p) != '}') {
            char key[32], value[COUNCIL_HOST_LENGTH];
            if (json_string(&p, key, sizeof(key)) || expect(&p, ':')) goto invalid;
            if (!strcmp(key, "port")) { char *end; long port; p = skip_space(p); port = strtol(p, &end, 10); if (end == p || port < 1 || port > 65535) goto invalid; item.port = (uint16_t)port; p = end; fields |= 8; }
            else if (!strcmp(key, "arbiter_priority")) { char *end; long priority; p = skip_space(p); priority = strtol(p, &end, 10); if (end == p || priority < 0 || priority > 1000000) goto invalid; item.arbiter_priority = (int)priority; p = end; }
            else { if (json_string(&p, value, sizeof(value))) goto invalid;
                if (!strcmp(key, "name")) { if (copy_value(item.name, sizeof(item.name), value)) goto invalid; fields |= 1; }
                else if (!strcmp(key, "role")) { if (!strcmp(value, "human")) item.role = CONTACT_HUMAN; else if (!strcmp(value, "ai")) item.role = CONTACT_AI; else goto invalid; fields |= 2; }
                else if (!strcmp(key, "host")) { if (copy_value(item.host, sizeof(item.host), value)) goto invalid; fields |= 4; }
                else if (!strcmp(key, "shared_key")) { if (copy_value(item.shared_key, sizeof(item.shared_key), value)) goto invalid; fields |= 16; }
                else goto invalid;
            }
            p = skip_space(p); if (*p == ',') p++; else if (*p != '}') goto invalid;
        }
        p++; if (fields != 31) goto invalid; book->items[book->count++] = item;
        p = skip_space(p); if (*p == ',') p++; else if (*p != ']') goto invalid;
    }
    p++; if (*skip_space(p)) goto invalid; free(text); return 0;
invalid:
    snprintf(error, error_size, "invalid contacts JSON near byte %ld", (long)(p - text)); free(text); return -1;
}
const contact *contact_book_find(const contact_book *book, const char *name) {
    size_t i; for (i = 0; i < book->count; i++) if (!strcmp(book->items[i].name, name)) return &book->items[i]; return NULL;
}
