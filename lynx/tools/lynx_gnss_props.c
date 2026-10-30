/* Bionic property stub for a RAM-only, network-isolated mnld startup audit.
 * Values come from Lynx's MT6983 kernel and the observed ADIE 0x6637 log.
 * This must not be installed as an Alpine service without a live audit.
 */

static int equal(const char *a, const char *b)
{
    while (*a && *b && *a == *b) { ++a; ++b; }
    return *a == *b;
}

static int copy(char *dst, const char *src)
{
    int n = 0;
    if (!src) src = "";
    while (src[n] && n < 91) { dst[n] = src[n]; ++n; }
    dst[n] = 0;
    return n;
}

static long syscall_openat(const char *path)
{
    register long x0 __asm__("x0") = -100;
    register long x1 __asm__("x1") = (long)path;
    register long x2 __asm__("x2") = 1089; /* O_WRONLY|O_CREAT|O_APPEND */
    register long x3 __asm__("x3") = 0600;
    register long x8 __asm__("x8") = 56;
    __asm__ volatile("svc 0" : "+r"(x0) : "r"(x1), "r"(x2), "r"(x3), "r"(x8) : "memory");
    return x0;
}

static void syscall_write(long fd, const char *value)
{
    long n = 0;
    register long x0 __asm__("x0") = fd;
    register long x1 __asm__("x1") = (long)value;
    register long x2 __asm__("x2");
    register long x8 __asm__("x8") = 64;
    if (!value) return;
    while (value[n]) ++n;
    x2 = n;
    __asm__ volatile("svc 0" : "+r"(x0) : "r"(x1), "r"(x2), "r"(x8) : "memory");
}

static void syscall_close(long fd)
{
    register long x0 __asm__("x0") = fd;
    register long x8 __asm__("x8") = 57;
    __asm__ volatile("svc 0" : "+r"(x0) : "r"(x8) : "memory");
}

static void record(const char *action, const char *key, const char *value)
{
    long fd = syscall_openat("/run/lynx-gnss-properties.log");
    if (fd < 0) return;
    syscall_write(fd, action);
    syscall_write(fd, " ");
    syscall_write(fd, key);
    syscall_write(fd, "=");
    syscall_write(fd, value);
    syscall_write(fd, "\n");
    syscall_close(fd);
}

__attribute__((visibility("default")))
int property_get(const char *key, char *value, const char *fallback)
{
    const char *chosen = fallback ? fallback : "";
    if (equal(key, "persist.vendor.connsys.chipid")) chosen = "0x6983";
    else if (equal(key, "vendor.connsys.adie.chipid")) chosen = "0x6637";
    else if (equal(key, "vendor.connsys.driver.ready")) chosen = "yes";
    else if (equal(key, "vendor.service.nvram_init")) chosen = "Ready";
    int n = copy(value, chosen);
    record("get", key, value);
    return n;
}

__attribute__((visibility("default")))
int property_set(const char *key, const char *value)
{
    record("set", key, value);
    return 0;
}
