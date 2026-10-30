/* Isolated constructor/load audit for the stock Android GNSS HAL.
 * Does not open the HAL or any GPS device node.
 */
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>

struct hw_module_methods {
    int (*open)(const void *, const char *, void **);
};

struct hw_module_header {
    uint32_t tag;
    uint16_t module_api_version;
    uint16_t hal_api_version;
    const char *id;
    const char *name;
    const char *author;
    struct hw_module_methods *methods;
};

int main(void)
{
    void *library = dlopen("/lib64/gps.default.so", RTLD_NOW | RTLD_LOCAL);
    if (!library) {
        fprintf(stderr, "hal_load_error=%s\n", dlerror());
        return 1;
    }
    struct hw_module_header *module = dlsym(library, "HAL_MODULE_INFO_SYM");
    if (!module) {
        fprintf(stderr, "hal_symbol_error=%s\n", dlerror());
        return 2;
    }
    printf("hal_tag=%08x api=%04x id=%s name=%s methods=%s\n",
           module->tag, module->module_api_version,
           module->id ? module->id : "(null)",
           module->name ? module->name : "(null)",
           module->methods && module->methods->open ? "present" : "absent");
    dlclose(library);
    return 0;
}
