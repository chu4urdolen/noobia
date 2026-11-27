/* Bionic property, wakelock, and logging shim for ccci_mdinit and ccci_rpcd.
 *
 * Ensures:
 * 1. prctl(PR_SET_NAME, "ccci_mdinit") on load.
 * 2. acquire_wake_lock and release_wake_lock return 0 without blocking on binder / servicemanager.
 * 3. Dynamic property storage for property_set / property_get.
 * 4. Platform default properties for MT6983 baseband.
 * 5. Intercepts __android_log_print and __android_log_buf_print to write to stderr (fd 2),
 *    making all internal CCCI daemon logs visible in /var/log/ccci_*.log!
 */

#define PR_SET_NAME 15
#define __NR_prctl 167

#define MAX_DYNAMIC_PROPS 64

struct prop_entry {
    char key[64];
    char val[96];
};

static struct prop_entry dynamic_props[MAX_DYNAMIC_PROPS];
static int dynamic_count = 0;

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

extern int vsnprintf(char *str, unsigned long size, const char *format, __builtin_va_list ap);
extern long write(int fd, const void *buf, unsigned long count);

__attribute__((visibility("default")))
int acquire_wake_lock(int lock, const char *id)
{
    return 0;
}

__attribute__((visibility("default")))
int release_wake_lock(const char *id)
{
    return 0;
}

__attribute__((visibility("default")))
int __android_log_print(int prio, const char *tag, const char *fmt, ...)
{
    char buf[1024];
    __builtin_va_list ap;
    __builtin_va_start(ap, fmt);
    int len = vsnprintf(buf, sizeof(buf) - 2, fmt, ap);
    __builtin_va_end(ap);

    if (len < 0) len = 0;
    if (len >= (int)sizeof(buf) - 2) len = sizeof(buf) - 2;
    if (len > 0 && buf[len - 1] != '\n') {
        buf[len++] = '\n';
        buf[len] = '\0';
    }

    if (tag) {
        write(2, "[", 1);
        int taglen = 0;
        while (tag[taglen]) ++taglen;
        write(2, tag, taglen);
        write(2, "] ", 2);
    }
    write(2, buf, len);
    return len;
}

__attribute__((visibility("default")))
int __android_log_buf_print(int bufID, int prio, const char *tag, const char *fmt, ...)
{
    char buf[1024];
    __builtin_va_list ap;
    __builtin_va_start(ap, fmt);
    int len = vsnprintf(buf, sizeof(buf) - 2, fmt, ap);
    __builtin_va_end(ap);

    if (len < 0) len = 0;
    if (len >= (int)sizeof(buf) - 2) len = sizeof(buf) - 2;
    if (len > 0 && buf[len - 1] != '\n') {
        buf[len++] = '\n';
        buf[len] = '\0';
    }

    if (tag) {
        write(2, "[", 1);
        int taglen = 0;
        while (tag[taglen]) ++taglen;
        write(2, tag, taglen);
        write(2, "] ", 2);
    }
    write(2, buf, len);
    return len;
}

__attribute__((constructor))
static void ccci_shim_init(void)
{
    /* Set comm to ccci_mdinit so CCCI driver validation succeeds */
    register long x0 __asm__("x0") = PR_SET_NAME;
    register long x1 __asm__("x1") = (long)"ccci_mdinit";
    register long x2 __asm__("x2") = 0;
    register long x3 __asm__("x3") = 0;
    register long x4 __asm__("x4") = 0;
    register long x8 __asm__("x8") = __NR_prctl;
    __asm__ volatile("svc 0" : "+r"(x0) : "r"(x1), "r"(x2), "r"(x3), "r"(x4), "r"(x8) : "memory");
}

__attribute__((visibility("default")))
int property_get(const char *key, char *value, const char *fallback)
{
    /* 1. Check dynamic properties set at runtime */
    for (int i = 0; i < dynamic_count; ++i) {
        if (equal(dynamic_props[i].key, key)) {
            return copy(value, dynamic_props[i].val);
        }
    }

    /* 2. Platform defaults */
    const char *chosen = fallback ? fallback : "";
    if (equal(key, "persist.vendor.connsys.chipid")) chosen = "0x6983";
    else if (equal(key, "vendor.connsys.adie.chipid")) chosen = "0x6637";
    else if (equal(key, "vendor.connsys.driver.ready")) chosen = "yes";
    else if (equal(key, "vendor.service.nvram_init")) chosen = "Ready";
    else if (equal(key, "ro.boot.fstab_suffix")) chosen = "mt6983";
    else if (equal(key, "ro.vendor.mtk_mipc_support")) chosen = "0";
    else if (equal(key, "ro.vendor.mtk_protocol1_rat_config")) chosen = "N/A";
    else if (equal(key, "persist.vendor.operator.subid")) chosen = "1";
    else if (equal(key, "vendor.mtk.md1.status")) chosen = "ready";
    else if (equal(key, "ro.vendor.mtk_md_sbp_custom_value")) chosen = "0";
    else if (equal(key, "vendor.mtk.md.sbp")) chosen = "0";
    else if (equal(key, "ro.vendor.mtk_ril_mode")) chosen = "c6m_1rild";
    else if (equal(key, "ro.telephony.sim.count")) chosen = "2";
    else if (equal(key, "ro.boot.opt_sim_count")) chosen = "2";
    else if (equal(key, "persist.vendor.radio.msimmode")) chosen = "dsds";
    else if (equal(key, "persist.radio.multisim.config")) chosen = "dsds";
    else if (equal(key, "ro.vendor.radio.max.multisim")) chosen = "dsds";
    else if (equal(key, "ro.vendor.mtk_sim_card_onoff")) chosen = "3";
    else if (equal(key, "persist.vendor.mtk_sim_switch_policy")) chosen = "2";
    else if (equal(key, "persist.vendor.radio.smart.data.switch")) chosen = "1";
    else if (equal(key, "ro.vendor.mtk_sim_hot_swap_common_slot")) chosen = "1";
    else if (equal(key, "persist.vendor.radio.mtk_dsbp_support")) chosen = "3";
    else if (equal(key, "init.svc.vendor.gsm0710muxd")) chosen = "running";
    else if (equal(key, "init.svc.vendor.ril-daemon-mtk")) chosen = "running";
    else if (equal(key, "init.svc.vendor.ril-proxy")) chosen = "running";
    else if (equal(key, "init.svc.emdlogger1")) chosen = "running";
    else if (equal(key, "init.svc.emdlogger2")) chosen = "running";
    else if (equal(key, "init.svc.emdlogger3")) chosen = "running";
    else if (equal(key, "init.svc.mdlogger")) chosen = "running";
    else if (equal(key, "init.svc.debuggerd")) chosen = "running";
    else if (equal(key, "ro.build.type")) chosen = "user";
    else if (equal(key, "persist.vendor.ccci.md1.dbg_dump")) chosen = "none";
    else if (equal(key, "persist.vendor.md.fsd.debug")) chosen = "none";
    else if (equal(key, "persist.vendor.md.fsd.log")) chosen = "0";

    return copy(value, chosen);
}

__attribute__((visibility("default")))
int property_set(const char *key, const char *value)
{
    /* Store into dynamic properties */
    for (int i = 0; i < dynamic_count; ++i) {
        if (equal(dynamic_props[i].key, key)) {
            copy(dynamic_props[i].val, value);
            return 0;
        }
    }

    if (dynamic_count < MAX_DYNAMIC_PROPS) {
        copy(dynamic_props[dynamic_count].key, key);
        copy(dynamic_props[dynamic_count].val, value);
        dynamic_count++;
    }

    return 0;
}
