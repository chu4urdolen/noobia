#ifndef NOOBIA_SHA256_H
#define NOOBIA_SHA256_H
#include <stddef.h>
#include <stdint.h>
typedef struct { uint32_t h[8]; uint64_t bits; uint8_t buf[64]; size_t used; } sha256_ctx;
void sha256_init(sha256_ctx *c);
void sha256_update(sha256_ctx *c, const void *data, size_t len);
void sha256_final(sha256_ctx *c, uint8_t out[32]);
void hmac_sha256(const uint8_t *key, size_t keylen, const uint8_t *data, size_t len, uint8_t out[32]);
#endif

