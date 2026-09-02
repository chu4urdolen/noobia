#ifndef NOOBIA_CONTACT_BOOK_H
#define NOOBIA_CONTACT_BOOK_H

#include <stddef.h>
#include <stdint.h>

#define COUNCIL_MAX_CONTACTS 64
#define COUNCIL_NAME_LENGTH 64
#define COUNCIL_HOST_LENGTH 256
#define COUNCIL_KEY_LENGTH 128

typedef enum { CONTACT_HUMAN = 1, CONTACT_AI = 2 } contact_role;

typedef struct {
    char name[COUNCIL_NAME_LENGTH];
    contact_role role;
    char host[COUNCIL_HOST_LENGTH];
    uint16_t port;
    char shared_key[COUNCIL_KEY_LENGTH];
    int arbiter_priority;
    unsigned int ram_gb;
} contact;

typedef struct {
    contact items[COUNCIL_MAX_CONTACTS];
    size_t count;
} contact_book;

int contact_book_load(const char *path, contact_book *book,
                      char *error, size_t error_size);
const contact *contact_book_find(const contact_book *book, const char *name);

#endif
