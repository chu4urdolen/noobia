/* Constructor-only HAL load check inside the RAM GNSS sandbox.
 * No GPS hardware method or device node is touched.
 */
#include <stdint.h>

extern void *dlopen(const char *, int);
extern void *dlsym(void *, const char *);
extern const char *dlerror(void);

struct hw_module_header {
    uint32_t tag;
    uint16_t module_api_version;
    uint16_t hal_api_version;
    const char *id;
    const char *name;
    const char *author;
    void *methods;
};

static void log_text(const char *text)
{
    register long x0 __asm__("x0") = -100;
    register long x1 __asm__("x1") = (long)"/run/lynx-gnss-hal-audit.log";
    register long x2 __asm__("x2") = 1089;
    register long x3 __asm__("x3") = 0600;
    register long x8 __asm__("x8") = 56;
    __asm__ volatile("svc 0" : "+r"(x0) : "r"(x1), "r"(x2), "r"(x3), "r"(x8) : "memory");
    long fd = x0;
    if (fd < 0) return;
    long length = 0;
    while (text[length] && length < 300) ++length;
    register long w0 __asm__("x0") = fd;
    register long w1 __asm__("x1") = (long)text;
    register long w2 __asm__("x2") = length;
    register long w8 __asm__("x8") = 64;
    __asm__ volatile("svc 0" : "+r"(w0) : "r"(w1), "r"(w2), "r"(w8) : "memory");
    register long c0 __asm__("x0") = fd;
    register long c8 __asm__("x8") = 57;
    __asm__ volatile("svc 0" : "+r"(c0) : "r"(c8) : "memory");
}

__attribute__((constructor)) static void audit_hal_load(void)
{
    log_text("audit_started\n");
    void *library = dlopen("/lib64/gps.default.so", 2);
    if (!library) {
        log_text("dlopen_failed: ");
        const char *error = dlerror();
        if (error) log_text(error);
        log_text("\n");
        return;
    }
    log_text("dlopen_ok\n");
    struct hw_module_header *module = dlsym(library, "HAL_MODULE_INFO_SYM");
    if (!module) {
        log_text("hal_symbol_missing\n");
        return;
    }
    log_text("hal_symbol_ok id=");
    if (module->id) log_text(module->id);
    log_text(" name=");
    if (module->name) log_text(module->name);
    log_text("\n");
}
