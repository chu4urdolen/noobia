#define _POSIX_C_SOURCE 200809L

#include "hue_client.h"

#include <arpa/inet.h>
#include <ctype.h>
#include <errno.h>
#include <math.h>
#include <netdb.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

static bool lock_owned = false;

static const char *lock_path(void)
{
    const char *path = getenv("ROSE_HUE_LOCK");
    return path != NULL && *path != '\0' ? path : "/tmp/rose-hue.lock";
}

static bool stale_lock(void)
{
    FILE *file = fopen(lock_path(), "r");
    long owner = 0;
    if (file == NULL) return false;
    if (fscanf(file, "%ld", &owner) != 1) owner = 0;
    fclose(file);
    return owner > 1 && kill((pid_t)owner, 0) != 0 && errno == ESRCH;
}

int hue_lock_acquire(unsigned int timeout_seconds, char *error, size_t error_size)
{
    struct timespec pause = {0, 100000000L};
    unsigned int attempts = timeout_seconds * 10U + 1U;
    for (unsigned int attempt = 0; attempt < attempts; attempt++) {
        int fd = open(lock_path(), O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
        if (fd >= 0) {
            char owner[64];
            int length = snprintf(owner, sizeof(owner), "%ld\n", (long)getpid());
            if (write(fd, owner, (size_t)length) != length) {
                close(fd);
                unlink(lock_path());
                snprintf(error, error_size, "cannot write Hue lock");
                return -1;
            }
            close(fd);
            lock_owned = true;
            return 0;
        }
        if (errno != EEXIST) {
            snprintf(error, error_size, "cannot create Hue lock: %s", strerror(errno));
            return -1;
        }
        if (stale_lock()) {
            (void)unlink(lock_path());
            continue;
        }
        if (attempt + 1U < attempts) nanosleep(&pause, NULL);
    }
    snprintf(error, error_size, "timed out waiting %u seconds for Hue lock", timeout_seconds);
    return -1;
}

void hue_lock_release(void)
{
    if (lock_owned) {
        (void)unlink(lock_path());
        lock_owned = false;
    }
}

void hue_lock_force_clear(void)
{
    (void)unlink(lock_path());
    lock_owned = false;
}

static void copy_value(char *destination, size_t size, const char *value)
{
    if (size == 0) return;
    snprintf(destination, size, "%s", value);
}

static char *trim(char *text)
{
    char *end;
    while (isspace((unsigned char)*text)) text++;
    end = text + strlen(text);
    while (end > text && isspace((unsigned char)end[-1])) end--;
    *end = '\0';
    return text;
}

static void load_file(struct hue_config *config)
{
    const char *explicit_path = getenv("ROSE_HUE_CONFIG");
    const char *home = getenv("HOME");
    char path[512];
    char line[1024];
    FILE *file;

    if (explicit_path != NULL && *explicit_path != '\0') {
        copy_value(path, sizeof(path), explicit_path);
    } else if (home != NULL && *home != '\0') {
        snprintf(path, sizeof(path), "%s/.config/rose-tools/hue.conf", home);
    } else {
        return;
    }
    file = fopen(path, "r");
    if (file == NULL) return;
    while (fgets(line, sizeof(line), file) != NULL) {
        char *key = trim(line);
        char *equals;
        char *value;
        if (*key == '\0' || *key == '#') continue;
        equals = strchr(key, '=');
        if (equals == NULL) continue;
        *equals = '\0';
        value = trim(equals + 1);
        key = trim(key);
        if (strcmp(key, "HUE_BRIDGE_IP") == 0) copy_value(config->bridge, sizeof(config->bridge), value);
        else if (strcmp(key, "HUE_USERNAME") == 0) copy_value(config->username, sizeof(config->username), value);
        else if (strcmp(key, "HUE_TARGET") == 0) copy_value(config->target, sizeof(config->target), value);
    }
    fclose(file);
}

int hue_config_load(struct hue_config *config)
{
    const char *value;
    memset(config, 0, sizeof(*config));
    copy_value(config->target, sizeof(config->target), "lights/1/state");
    load_file(config);
    value = getenv("HUE_BRIDGE_IP");
    if (value != NULL && *value != '\0') copy_value(config->bridge, sizeof(config->bridge), value);
    value = getenv("HUE_USERNAME");
    if (value != NULL && *value != '\0') copy_value(config->username, sizeof(config->username), value);
    value = getenv("HUE_TARGET");
    if (value != NULL && *value != '\0') copy_value(config->target, sizeof(config->target), value);
    if (*config->bridge == '\0' || *config->username == '\0') return -1;
    return 0;
}

static double gamma_expand(double component)
{
    component /= 255.0;
    return component > 0.04045 ? pow((component + 0.055) / 1.055, 2.4)
                               : component / 12.92;
}

static void rgb_to_xy(unsigned int red, unsigned int green, unsigned int blue,
                      double *x, double *y)
{
    double r = gamma_expand(red), g = gamma_expand(green), b = gamma_expand(blue);
    double X = r * 0.664511 + g * 0.154324 + b * 0.162028;
    double Y = r * 0.283881 + g * 0.668433 + b * 0.047685;
    double Z = r * 0.000088 + g * 0.072310 + b * 0.986039;
    double sum = X + Y + Z;
    if (sum <= 0.0) {
        *x = 0.3127;
        *y = 0.3290;
    } else {
        *x = X / sum;
        *y = Y / sum;
    }
}

static int send_all(int socket_fd, const char *data, size_t length)
{
    while (length > 0) {
        ssize_t sent = send(socket_fd, data, length, MSG_NOSIGNAL);
        if (sent < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        data += sent;
        length -= (size_t)sent;
    }
    return 0;
}

int hue_set_rgb(const struct hue_config *config, unsigned int red, unsigned int green,
                unsigned int blue, unsigned int brightness, double transition_seconds,
                char *error, size_t error_size)
{
    struct addrinfo hints = {0}, *addresses = NULL, *address;
    struct timeval timeout = {2, 0};
    char path[768], body[256], request[1536], response[4096];
    int socket_fd = -1, body_length, request_length;
    size_t used = 0;
    double x, y;
    unsigned int hue_brightness, transition;

    rgb_to_xy(red, green, blue, &x, &y);
    hue_brightness = brightness == 0 ? 1 : (brightness * 253U) / 255U + 1U;
    transition = (unsigned int)(transition_seconds * 10.0 + 0.5);
    if (transition > 65535U) transition = 65535U;
    if (brightness == 0) body_length = snprintf(body, sizeof(body), "{\"on\":false,\"transitiontime\":%u}", transition);
    else body_length = snprintf(body, sizeof(body), "{\"on\":true,\"xy\":[%.6f,%.6f],\"bri\":%u,\"transitiontime\":%u}", x, y, hue_brightness, transition);
    snprintf(path, sizeof(path), "/api/%s/%s", config->username, config->target);
    request_length = snprintf(request, sizeof(request),
        "PUT %s HTTP/1.1\r\nHost: %s\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s",
        path, config->bridge, body_length, body);
    if (body_length < 0 || request_length < 0 || (size_t)request_length >= sizeof(request)) {
        snprintf(error, error_size, "request is too large");
        return -1;
    }
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    if (getaddrinfo(config->bridge, "80", &hints, &addresses) != 0) {
        snprintf(error, error_size, "cannot resolve Hue bridge");
        return -1;
    }
    for (address = addresses; address != NULL; address = address->ai_next) {
        socket_fd = socket(address->ai_family, address->ai_socktype, address->ai_protocol);
        if (socket_fd < 0) continue;
        setsockopt(socket_fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
        setsockopt(socket_fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
        if (connect(socket_fd, address->ai_addr, address->ai_addrlen) == 0) break;
        close(socket_fd);
        socket_fd = -1;
    }
    freeaddrinfo(addresses);
    if (socket_fd < 0 || send_all(socket_fd, request, (size_t)request_length) != 0) {
        if (socket_fd >= 0) close(socket_fd);
        snprintf(error, error_size, "cannot contact Hue bridge");
        return -1;
    }
    while (used + 1 < sizeof(response)) {
        ssize_t count = recv(socket_fd, response + used, sizeof(response) - used - 1, 0);
        if (count == 0) break;
        if (count < 0) {
            if (errno == EINTR) continue;
            break;
        }
        used += (size_t)count;
    }
    close(socket_fd);
    response[used] = '\0';
    if (strstr(response, " 200 ") == NULL || strstr(response, "\"success\"") == NULL) {
        snprintf(error, error_size, "Hue bridge rejected the update");
        return -1;
    }
    return 0;
}

int hue_dark(const struct hue_config *config, char *error, size_t error_size)
{
    return hue_set_rgb(config, 0, 0, 0, 0, 0.2, error, error_size);
}
