/* ARM64 Linux syscall runtime for isolated VM tests only; never part of a DA payload. */
#include "test_runtime.h"
void *memcpy(void *dst, const void *src, usize count)
{
    unsigned char *out = dst; const unsigned char *in = src;
    for (usize i = 0; i < count; i++) out[i] = in[i];
    return dst;
}
void *memset(void *dst, int value, usize count)
{
    unsigned char *out = dst;
    for (usize i = 0; i < count; i++) out[i] = (unsigned char)value;
    return dst;
}
int memcmp(const void *left, const void *right, usize count)
{
    const unsigned char *a = left, *b = right;
    for (usize i = 0; i < count; i++) if (a[i] != b[i]) return a[i] - b[i];
    return 0;
}
int strcmp(const char *a, const char *b)
{
    while (*a && *a == *b) { a++; b++; }
    return (unsigned char)*a - (unsigned char)*b;
}
char *strstr(const char *text, const char *needle)
{
    for (; *text; text++) {
        usize i = 0;
        while (needle[i] && text[i] == needle[i]) i++;
        if (!needle[i]) return (char *)text;
    }
    return 0;
}
static long call(long number, long a, long b, long c)
{
    register long x0 __asm__("x0") = a;
    register long x1 __asm__("x1") = b;
    register long x2 __asm__("x2") = c;
    register long x8 __asm__("x8") = number;
    __asm__ volatile("svc 0" : "+r"(x0) : "r"(x1), "r"(x2), "r"(x8) : "memory");
    return x0;
}
int puts(const char *text)
{
    usize count = 0;
    while (text[count]) count++;
    if (call(64, 1, (long)text, count) != (long)count) return -1;
    return call(64, 1, (long)"\n", 1) == 1 ? 0 : -1;
}
void lynx_test_failed(int line)
{
    (void)line;
    puts("LYNX_READER_ARM_TEST_FAILED");
    call(93, 1, 0, 0);
    for (;;) {}
}
void _start(void)
{
    extern int main(void);
    int result = main();
    if (result == 0) puts("LYNX_READER_ARM_TEST_PASSED");
    call(93, result, 0, 0);
    for (;;) {}
}
