#ifndef NOOBIA_AUTHENTICATION_H
#define NOOBIA_AUTHENTICATION_H
#include <stddef.h>
int authentication_nonce(char output[33]);
void authentication_digest(const char *key, const char *name,
                           const char *nonce, char output[65]);
int authentication_matches(const char *left, const char *right);
#endif

