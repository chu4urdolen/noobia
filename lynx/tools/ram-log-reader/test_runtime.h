#ifndef LYNX_TEST_RUNTIME_H
#define LYNX_TEST_RUNTIME_H
typedef __SIZE_TYPE__ usize;
void *memcpy(void *, const void *, usize);
void *memset(void *, int, usize);
int memcmp(const void *, const void *, usize);
int strcmp(const char *, const char *);
char *strstr(const char *, const char *);
int puts(const char *);
void lynx_test_failed(int) __attribute__((noreturn));
#define assert(value) do { if (!(value)) lynx_test_failed(__LINE__); } while (0)
#endif
