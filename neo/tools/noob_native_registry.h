#pragma once

#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

/* Linux native calls use the same bounded numeric + ASCII shape as ESP calls. */
typedef struct {
  int32_t numbers[8];
  unsigned count;
  char ascii[192];
} NoobNativeArguments;

typedef void (*NoobNativeFunction)(int, unsigned, const char *,
                                   const NoobNativeArguments *);
typedef struct {
  const char *name;
  unsigned numbers;
  int text;
  NoobNativeFunction call;
} NoobNativeEntry;

static inline const NoobNativeEntry *noob_native_find(
    const NoobNativeEntry *entries, unsigned count, const char *name) {
  for (unsigned i = 0; i < count; ++i)
    if (!strcmp(entries[i].name, name)) return &entries[i];
  return NULL;
}

static inline int noob_native_parse(const char *text, int mixed,
                                     NoobNativeArguments *out) {
  memset(out, 0, sizeof(*out));
  while (*text == ' ') ++text;
  while (*text && *text != '"') {
    if (out->count == 8) return 0;
    char *end;
    errno = 0;
    long value = strtol(text, &end, 10);
    if (errno || end == text || value < INT32_MIN || value > INT32_MAX ||
        (*end && *end != ' ')) return 0;
    out->numbers[out->count++] = (int32_t)value;
    text = end;
    while (*text == ' ') ++text;
  }
  if (!mixed) return !*text;
  if (*text++ != '"') return 0;
  unsigned used = 0;
  while (*text && *text != '"') {
    unsigned char c = (unsigned char)*text++;
    if (c == '\\') {
      c = (unsigned char)*text++;
      if (c != '\\' && c != '"') return 0;
    }
    if (c < 32 || c > 126 || used + 1 >= sizeof(out->ascii)) return 0;
    out->ascii[used++] = (char)c;
  }
  if (*text++ != '"') return 0;
  while (*text == ' ') ++text;
  return !*text;
}
