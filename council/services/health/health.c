#define _DEFAULT_SOURCE
#define _POSIX_C_SOURCE 200809L

#include <dirent.h>
#include <errno.h>
#include <limits.h>
#include <arpa/inet.h>
#include <fcntl.h>
#include <netdb.h>
#include <poll.h>
#include <signal.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/statvfs.h>
#include <sys/socket.h>
#include <syslog.h>
#include <time.h>
#include <unistd.h>

#define DEFAULT_INTERVAL 60U
#define DEFAULT_DISK_WARN 90.0
#define DEFAULT_MEMORY_WARN 90.0
#define DEFAULT_TEMP_WARN 80.0
#define DEFAULT_CONTACTS_FILE "/etc/noobia-council/contacts.json"

static volatile sig_atomic_t running = 1;
static bool log_to_syslog = true;

static void stop_running(int signal_number)
{
    (void)signal_number;
    running = 0;
}

static void report(int priority, const char *format, ...)
{
    va_list arguments;

    va_start(arguments, format);
    if (log_to_syslog) {
        vsyslog(priority, format, arguments);
    } else {
        vfprintf(priority <= LOG_WARNING ? stderr : stdout, format, arguments);
        fputc('\n', priority <= LOG_WARNING ? stderr : stdout);
    }
    va_end(arguments);
}

static bool parse_double_env(const char *name, double fallback, double *value)
{
    const char *text = getenv(name);
    char *end = NULL;
    double parsed;

    if (text == NULL || *text == '\0') {
        *value = fallback;
        return true;
    }
    errno = 0;
    parsed = strtod(text, &end);
    if (errno != 0 || end == text || *end != '\0' || parsed < 0.0 || parsed > 100.0) {
        report(LOG_ERR, "invalid %s=%s (expected a number from 0 to 100)", name, text);
        return false;
    }
    *value = parsed;
    return true;
}

static bool parse_interval(unsigned int *interval)
{
    const char *text = getenv("HEALTH_INTERVAL_SECONDS");
    char *end = NULL;
    unsigned long parsed;

    if (text == NULL || *text == '\0') {
        *interval = DEFAULT_INTERVAL;
        return true;
    }
    errno = 0;
    parsed = strtoul(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0' || parsed == 0 || parsed > UINT_MAX) {
        report(LOG_ERR, "invalid HEALTH_INTERVAL_SECONDS=%s", text);
        return false;
    }
    *interval = (unsigned int)parsed;
    return true;
}

static void check_disk(double warning_percent)
{
    struct statvfs information;
    double used_percent;

    if (statvfs("/", &information) != 0) {
        report(LOG_ERR, "disk check failed: %s", strerror(errno));
        return;
    }
    if (information.f_blocks == 0) {
        report(LOG_WARNING, "disk check returned zero filesystem blocks");
        return;
    }
    used_percent = 100.0 * (1.0 - (double)information.f_bavail /
                                      (double)information.f_blocks);
    report(used_percent >= warning_percent ? LOG_WARNING : LOG_INFO,
           "disk root used=%.1f%% threshold=%.1f%%", used_percent, warning_percent);
}

static void check_memory(double warning_percent)
{
    FILE *file = fopen("/proc/meminfo", "r");
    char line[256];
    unsigned long long total = 0;
    unsigned long long available = 0;

    if (file == NULL) {
        report(LOG_ERR, "memory check failed: %s", strerror(errno));
        return;
    }
    while (fgets(line, sizeof(line), file) != NULL) {
        (void)sscanf(line, "MemTotal: %llu kB", &total);
        (void)sscanf(line, "MemAvailable: %llu kB", &available);
    }
    fclose(file);
    if (total == 0) {
        report(LOG_ERR, "memory check could not read MemTotal");
        return;
    }
    double used_percent = 100.0 * (1.0 - (double)available / (double)total);
    report(used_percent >= warning_percent ? LOG_WARNING : LOG_INFO,
           "memory used=%.1f%% threshold=%.1f%%", used_percent, warning_percent);
}

static void check_load(void)
{
    double load[3];
    long processors = sysconf(_SC_NPROCESSORS_ONLN);

    if (getloadavg(load, 3) != 3) {
        report(LOG_ERR, "load check failed");
        return;
    }
    report(processors > 0 && load[0] > (double)processors ? LOG_WARNING : LOG_INFO,
           "load averages=%.2f,%.2f,%.2f online_cpus=%ld", load[0], load[1], load[2],
           processors);
}

static void check_temperatures(double warning_celsius)
{
    DIR *directory = opendir("/sys/class/thermal");
    struct dirent *entry;
    unsigned int sensors = 0;

    if (directory == NULL) {
        report(LOG_INFO, "temperature sensors unavailable: %s", strerror(errno));
        return;
    }
    while ((entry = readdir(directory)) != NULL) {
        char path[PATH_MAX];
        char type_path[PATH_MAX];
        char sensor_name[128] = "unknown";
        long millidegrees;
        FILE *file;

        if (strncmp(entry->d_name, "thermal_zone", 12) != 0) {
            continue;
        }
        if (snprintf(path, sizeof(path), "/sys/class/thermal/%s/temp", entry->d_name) >=
            (int)sizeof(path)) {
            continue;
        }
        file = fopen(path, "r");
        if (file == NULL || fscanf(file, "%ld", &millidegrees) != 1) {
            if (file != NULL) fclose(file);
            continue;
        }
        fclose(file);
        sensors++;

        if (snprintf(type_path, sizeof(type_path), "/sys/class/thermal/%s/type",
                     entry->d_name) < (int)sizeof(type_path)) {
            file = fopen(type_path, "r");
            if (file != NULL) {
                if (fgets(sensor_name, sizeof(sensor_name), file) != NULL) {
                    sensor_name[strcspn(sensor_name, "\r\n")] = '\0';
                }
                fclose(file);
            }
        }
        double celsius = (double)millidegrees / 1000.0;
        report(celsius >= warning_celsius ? LOG_WARNING : LOG_INFO,
               "temperature sensor=%s value=%.1fC threshold=%.1fC", sensor_name,
               celsius, warning_celsius);
    }
    closedir(directory);
    if (sensors == 0) {
        report(LOG_INFO, "temperature sensors unavailable: none detected");
    }
}

static bool json_string(const char *object, const char *key, char *value, size_t size)
{
    char pattern[128];
    const char *cursor;
    size_t used = 0;
    snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    cursor = strstr(object, pattern);
    if (cursor == NULL || (cursor = strchr(cursor + strlen(pattern), ':')) == NULL) return false;
    cursor++;
    while (*cursor == ' ' || *cursor == '\t' || *cursor == '\r' || *cursor == '\n') cursor++;
    if (*cursor++ != '\"') return false;
    while (*cursor != '\0' && *cursor != '\"') {
        if (*cursor == '\\' && cursor[1] != '\0') cursor++;
        if (used + 1 >= size) return false;
        value[used++] = *cursor++;
    }
    value[used] = '\0';
    return *cursor == '\"';
}

static bool json_port(const char *object, unsigned int *port)
{
    const char *cursor = strstr(object, "\"port\"");
    char *end;
    unsigned long parsed;
    if (cursor == NULL || (cursor = strchr(cursor + 6, ':')) == NULL) return false;
    errno = 0;
    parsed = strtoul(cursor + 1, &end, 10);
    if (errno != 0 || end == cursor + 1 || parsed == 0 || parsed > 65535) return false;
    *port = (unsigned int)parsed;
    return true;
}

static bool local_numeric_ip(const char *host)
{
    struct in_addr ipv4;
    struct in6_addr ipv6;
    if (inet_pton(AF_INET, host, &ipv4) == 1) {
        unsigned long address = ntohl(ipv4.s_addr);
        return (address >> 24) == 10 || (address >> 20) == 0xac1 ||
               (address >> 16) == 0xc0a8 || (address >> 24) == 127 ||
               (address >> 16) == 0xa9fe;
    }
    if (inet_pton(AF_INET6, host, &ipv6) == 1) {
        return IN6_IS_ADDR_LOOPBACK(&ipv6) || IN6_IS_ADDR_LINKLOCAL(&ipv6) ||
               (ipv6.s6_addr[0] & 0xfe) == 0xfc;
    }
    return false;
}

static bool endpoint_online(const char *host, unsigned int port)
{
    struct addrinfo hints = {0}, *addresses = NULL, *address;
    char service[16];
    bool online = false;
    snprintf(service, sizeof(service), "%u", port);
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_flags = AI_NUMERICHOST;
    if (getaddrinfo(host, service, &hints, &addresses) != 0) return false;
    for (address = addresses; address != NULL && !online; address = address->ai_next) {
        int fd = socket(address->ai_family, address->ai_socktype | SOCK_CLOEXEC, address->ai_protocol);
        if (fd < 0) continue;
        int flags = fcntl(fd, F_GETFL, 0);
        if (flags >= 0) (void)fcntl(fd, F_SETFL, flags | O_NONBLOCK);
        if (connect(fd, address->ai_addr, address->ai_addrlen) == 0) {
            online = true;
        } else if (errno == EINPROGRESS) {
            struct pollfd poll_fd = {fd, POLLOUT, 0};
            if (poll(&poll_fd, 1, 1000) > 0) {
                int socket_error = 0;
                socklen_t length = sizeof(socket_error);
                if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &socket_error, &length) == 0 &&
                    socket_error == 0) online = true;
            }
        }
        close(fd);
    }
    freeaddrinfo(addresses);
    return online;
}

static void check_contacts(void)
{
    const char *path = getenv("HEALTH_CONTACTS_FILE");
    FILE *file;
    char *document;
    long length;
    size_t checked = 0;
    if (path == NULL || *path == '\0') path = DEFAULT_CONTACTS_FILE;
    file = fopen(path, "r");
    if (file == NULL) {
        report(LOG_WARNING, "contact check unavailable file=%s error=%s", path, strerror(errno));
        return;
    }
    if (fseek(file, 0, SEEK_END) != 0 || (length = ftell(file)) < 0 || length > 1048576 ||
        fseek(file, 0, SEEK_SET) != 0) {
        report(LOG_ERR, "contact file invalid file=%s", path);
        fclose(file);
        return;
    }
    document = malloc((size_t)length + 1);
    if (document == NULL || fread(document, 1, (size_t)length, file) != (size_t)length) {
        report(LOG_ERR, "contact file read failed file=%s", path);
        free(document);
        fclose(file);
        return;
    }
    document[length] = '\0';
    fclose(file);
    for (char *start = document; (start = strchr(start, '{')) != NULL; ) {
        char *end = strchr(start, '}');
        char name[128], role[32], host[INET6_ADDRSTRLEN];
        unsigned int port;
        if (end == NULL) break;
        char saved = end[1];
        end[1] = '\0';
        if (json_string(start, "name", name, sizeof(name)) &&
            json_string(start, "role", role, sizeof(role)) && strcmp(role, "ai") == 0 &&
            json_string(start, "host", host, sizeof(host)) && local_numeric_ip(host) &&
            json_port(start, &port)) {
            bool online = endpoint_online(host, port);
            report(online ? LOG_INFO : LOG_WARNING,
                   "contact name=%s host=%s port=%u status=%s", name, host, port,
                   online ? "online" : "offline");
            checked++;
        }
        end[1] = saved;
        start = end + 1;
    }
    if (checked == 0) report(LOG_INFO, "contact check found no local AI endpoints file=%s", path);
    free(document);
}

static void run_checks(double disk_warning, double memory_warning, double temp_warning)
{
    check_disk(disk_warning);
    check_memory(memory_warning);
    check_load();
    check_temperatures(temp_warning);
    check_contacts();
}

static void usage(const char *program)
{
    fprintf(stderr, "Usage: %s [--once]\n", program);
}

int main(int argc, char **argv)
{
    bool once = false;
    unsigned int interval;
    double disk_warning;
    double memory_warning;
    double temp_warning;

    if (argc == 2 && strcmp(argv[1], "--once") == 0) {
        once = true;
        log_to_syslog = false;
    } else if (argc != 1) {
        usage(argv[0]);
        return EXIT_FAILURE;
    }
    if (!parse_interval(&interval) ||
        !parse_double_env("HEALTH_DISK_WARN_PERCENT", DEFAULT_DISK_WARN, &disk_warning) ||
        !parse_double_env("HEALTH_MEMORY_WARN_PERCENT", DEFAULT_MEMORY_WARN,
                          &memory_warning) ||
        !parse_double_env("HEALTH_TEMP_WARN_C", DEFAULT_TEMP_WARN, &temp_warning)) {
        return EXIT_FAILURE;
    }

    if (!once) {
        openlog("noobia-health", LOG_PID, LOG_DAEMON);
        signal(SIGTERM, stop_running);
        signal(SIGINT, stop_running);
        report(LOG_INFO, "health service started interval=%us", interval);
    }
    do {
        struct timespec remaining = {(time_t)interval, 0};
        run_checks(disk_warning, memory_warning, temp_warning);
        if (once) break;
        while (running && nanosleep(&remaining, &remaining) != 0 && errno == EINTR) {
        }
    } while (running);

    if (!once) {
        report(LOG_INFO, "health service stopped");
        closelog();
    }
    return EXIT_SUCCESS;
}
