#define _XOPEN_SOURCE 700

#include <arpa/inet.h>
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define PROJECTOR_MAC "30:4a:26:07:94:26"
#define PROJECTOR_NAME "Hccast-079426_dlna"
#define DLNA_PORT 49595
#define SERVICE "urn:schemas-upnp-org:service:AVTransport:1"

static void fail(const char *format, ...)
{
    va_list arguments;
    va_start(arguments, format);
    vfprintf(stderr, format, arguments);
    va_end(arguments);
    fputc('\n', stderr);
    exit(EXIT_FAILURE);
}

static void copy_text(char *destination, size_t size, const char *source)
{
    if (snprintf(destination, size, "%s", source) >= (int)size)
        fail("value is too long");
}

static int connect_tcp(const char *host, unsigned short port)
{
    int descriptor = socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in address = { .sin_family = AF_INET, .sin_port = htons(port) };
    struct timeval timeout = { .tv_sec = 8 };
    if (descriptor < 0 || inet_pton(AF_INET, host, &address.sin_addr) != 1)
        return -1;
    setsockopt(descriptor, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    setsockopt(descriptor, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
    if (connect(descriptor, (struct sockaddr *)&address, sizeof(address)) < 0) {
        close(descriptor);
        return -1;
    }
    return descriptor;
}

static ssize_t send_all(int descriptor, const void *buffer, size_t length)
{
    const char *cursor = buffer;
    size_t sent = 0;
    while (sent < length) {
        ssize_t count = send(descriptor, cursor + sent, length - sent, MSG_NOSIGNAL);
        if (count <= 0)
            return -1;
        sent += (size_t)count;
    }
    return (ssize_t)sent;
}

static char *receive_all(int descriptor)
{
    size_t used = 0, capacity = 8192;
    char *result = malloc(capacity);
    if (!result)
        fail("out of memory");
    for (;;) {
        if (used + 4096 + 1 > capacity) {
            capacity *= 2;
            char *grown = realloc(result, capacity);
            if (!grown) {
                free(result);
                fail("out of memory");
            }
            result = grown;
        }
        ssize_t count = recv(descriptor, result + used, capacity - used - 1, 0);
        if (count == 0)
            break;
        if (count < 0) {
            if (errno == EINTR)
                continue;
            break;
        }
        used += (size_t)count;
    }
    result[used] = '\0';
    return result;
}

static void local_ip(char output[INET_ADDRSTRLEN])
{
    int descriptor = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in remote = { .sin_family = AF_INET, .sin_port = htons(9) };
    struct sockaddr_in local;
    socklen_t length = sizeof(local);
    inet_pton(AF_INET, "192.168.100.1", &remote.sin_addr);
    if (descriptor < 0 || connect(descriptor, (struct sockaddr *)&remote, sizeof(remote)) < 0 ||
        getsockname(descriptor, (struct sockaddr *)&local, &length) < 0 ||
        !inet_ntop(AF_INET, &local.sin_addr, output, INET_ADDRSTRLEN))
        fail("cannot determine the Noobia interface address");
    close(descriptor);
}

static void find_projector(char output[INET_ADDRSTRLEN])
{
    char local[INET_ADDRSTRLEN], prefix[64];
    unsigned int a, b, c, d;
    local_ip(local);
    if (sscanf(local, "%u.%u.%u.%u", &a, &b, &c, &d) != 4)
        fail("unexpected local address: %s", local);
    snprintf(prefix, sizeof(prefix), "%u.%u.%u", a, b, c);

    int probe = socket(AF_INET, SOCK_DGRAM, 0);
    if (probe < 0)
        fail("cannot open discovery socket");
    for (unsigned int host = 1; host < 255; host++) {
        char candidate[128];
        struct sockaddr_in address = { .sin_family = AF_INET, .sin_port = htons(9) };
        snprintf(candidate, sizeof(candidate), "%s.%u", prefix, host);
        inet_pton(AF_INET, candidate, &address.sin_addr);
        (void)sendto(probe, "\0", 1, MSG_DONTWAIT, (struct sockaddr *)&address, sizeof(address));
    }
    close(probe);
    struct timespec delay = { .tv_sec = 1, .tv_nsec = 200000000 };
    nanosleep(&delay, NULL);

    FILE *table = fopen("/proc/net/arp", "r");
    if (!table)
        fail("cannot read the ARP table");
    char line[512];
    (void)fgets(line, sizeof(line), table);
    while (fgets(line, sizeof(line), table)) {
        char ip[64], hardware[64];
        if (sscanf(line, "%63s %*s %*s %63s", ip, hardware) == 2 &&
            strcasecmp(hardware, PROJECTOR_MAC) == 0) {
            copy_text(output, INET_ADDRSTRLEN, ip);
            fclose(table);
            return;
        }
    }
    fclose(table);
    fail("projector MAC %s was not found on %s.0/24", PROJECTOR_MAC, prefix);
}

static char *http_get(const char *host, const char *path)
{
    int descriptor = connect_tcp(host, DLNA_PORT);
    if (descriptor < 0)
        fail("cannot connect to the projector DLNA service at %s:%d", host, DLNA_PORT);
    char request[1024];
    int length = snprintf(request, sizeof(request),
        "GET %s HTTP/1.1\r\nHost: %s:%d\r\nConnection: close\r\n\r\n", path, host, DLNA_PORT);
    if (length < 0 || (size_t)length >= sizeof(request) || send_all(descriptor, request, (size_t)length) < 0)
        fail("failed to request the projector description");
    char *response = receive_all(descriptor);
    close(descriptor);
    return response;
}

static void extract_control_path(const char *description, char output[512])
{
    if (!strstr(description, " 200 ") || !strstr(description, PROJECTOR_NAME))
        fail("the MAC address did not resolve to the expected HCCast renderer");
    const char *service = strstr(description, SERVICE);
    const char *open = service ? strstr(service, "<controlURL>") : NULL;
    const char *close = open ? strstr(open, "</controlURL>") : NULL;
    if (!open || !close)
        fail("AVTransport control endpoint is missing");
    open += strlen("<controlURL>");
    size_t length = (size_t)(close - open);
    if (length == 0 || length >= 512)
        fail("invalid AVTransport control endpoint");
    memcpy(output, open, length);
    output[length] = '\0';
}

static bool soap(const char *host, const char *path, const char *action, const char *inner)
{
    char body[4096], header[2048];
    int body_length = snprintf(body, sizeof(body),
        "<?xml version=\"1.0\"?><s:Envelope xmlns:s=\"http://schemas.xmlsoap.org/soap/envelope/\" "
        "s:encodingStyle=\"http://schemas.xmlsoap.org/soap/encoding/\"><s:Body><u:%s xmlns:u=\"%s\">"
        "<InstanceID>0</InstanceID>%s</u:%s></s:Body></s:Envelope>", action, SERVICE, inner, action);
    int header_length = snprintf(header, sizeof(header),
        "POST %s HTTP/1.1\r\nHost: %s:%d\r\nContent-Type: text/xml; charset=\"utf-8\"\r\n"
        "SOAPACTION: \"%s#%s\"\r\nContent-Length: %d\r\nConnection: close\r\n\r\n",
        path, host, DLNA_PORT, SERVICE, action, body_length);
    if (body_length < 0 || header_length < 0 || (size_t)body_length >= sizeof(body) ||
        (size_t)header_length >= sizeof(header))
        fail("DLNA request is too large");
    int descriptor = connect_tcp(host, DLNA_PORT);
    if (descriptor < 0 || send_all(descriptor, header, (size_t)header_length) < 0 ||
        send_all(descriptor, body, (size_t)body_length) < 0) {
        if (descriptor >= 0)
            close(descriptor);
        return false;
    }
    char status[64] = {0};
    ssize_t count = recv(descriptor, status, sizeof(status) - 1, 0);
    close(descriptor);
    return count > 0 && strstr(status, " 200 ") != NULL;
}

static bool image_extension(const char *path)
{
    const char *dot = strrchr(path, '.');
    static const char *extensions[] = { ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp" };
    if (!dot)
        return false;
    for (size_t index = 0; index < sizeof(extensions) / sizeof(extensions[0]); index++)
        if (strcasecmp(dot, extensions[index]) == 0)
            return true;
    return false;
}

static void run_ffmpeg(const char *source, const char *output, bool image)
{
    pid_t child = fork();
    if (child < 0)
        fail("cannot start ffmpeg");
    if (child == 0) {
        const char *filter = "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:black";
        if (image)
            execlp("ffmpeg", "ffmpeg", "-y", "-loglevel", "error", "-i", source,
                "-vf", filter, "-q:v", "2", output, (char *)NULL);
        else
            execlp("ffmpeg", "ffmpeg", "-y", "-loglevel", "error", "-i", source,
                "-vf", filter, "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
                output, (char *)NULL);
        _exit(127);
    }
    int status;
    if (waitpid(child, &status, 0) < 0 || !WIFEXITED(status) || WEXITSTATUS(status) != 0)
        fail("ffmpeg could not prepare the media");
}

static int create_server(const char *bind_ip, unsigned short *port)
{
    int descriptor = socket(AF_INET, SOCK_STREAM, 0);
    int enabled = 1;
    struct sockaddr_in address = { .sin_family = AF_INET, .sin_port = 0 };
    socklen_t length = sizeof(address);
    inet_pton(AF_INET, bind_ip, &address.sin_addr);
    if (descriptor < 0 || setsockopt(descriptor, SOL_SOCKET, SO_REUSEADDR, &enabled, sizeof(enabled)) < 0 ||
        bind(descriptor, (struct sockaddr *)&address, sizeof(address)) < 0 || listen(descriptor, 1) < 0 ||
        getsockname(descriptor, (struct sockaddr *)&address, &length) < 0)
        fail("cannot start the local media server");
    *port = ntohs(address.sin_port);
    return descriptor;
}

static void serve_once(int server, const char *media, const char *name)
{
    alarm(20);
    int client = accept(server, NULL, NULL);
    if (client < 0)
        _exit(2);
    char request[2048];
    ssize_t count = recv(client, request, sizeof(request) - 1, 0);
    if (count <= 0)
        _exit(3);
    request[count] = '\0';
    char expected[512];
    snprintf(expected, sizeof(expected), "GET /%s ", name);
    if (strncmp(request, expected, strlen(expected)) != 0)
        _exit(4);
    int file = open(media, O_RDONLY);
    struct stat info;
    if (file < 0 || fstat(file, &info) < 0)
        _exit(5);
    char header[512];
    int header_length = snprintf(header, sizeof(header),
        "HTTP/1.1 200 OK\r\nContent-Length: %lld\r\nContent-Type: application/octet-stream\r\nConnection: close\r\n\r\n",
        (long long)info.st_size);
    if (send_all(client, header, (size_t)header_length) < 0)
        _exit(6);
    char buffer[65536];
    while ((count = read(file, buffer, sizeof(buffer))) > 0)
        if (send_all(client, buffer, (size_t)count) < 0)
            _exit(7);
    close(file);
    close(client);
    close(server);
    _exit(count < 0 ? 8 : 0);
}

int main(int argc, char **argv)
{
    if (argc != 2) {
        fprintf(stderr, "Usage: %s MEDIA\n", argv[0]);
        return EXIT_FAILURE;
    }
    char source[4096];
    if (!realpath(argv[1], source))
        fail("media file not found: %s", argv[1]);
    struct stat source_info;
    if (stat(source, &source_info) < 0 || !S_ISREG(source_info.st_mode))
        fail("not a regular media file: %s", source);

    char host[INET_ADDRSTRLEN], local[INET_ADDRSTRLEN], control[512];
    find_projector(host);
    local_ip(local);
    char *description = http_get(host, "/description.xml");
    extract_control_path(description, control);
    free(description);

    char temporary[] = "/tmp/rose-projector-XXXXXX";
    if (!mkdtemp(temporary))
        fail("cannot create temporary media directory");
    bool image = image_extension(source);
    const char *name = image ? "projector-image.jpg" : "projector-video.mp4";
    char media[4096];
    snprintf(media, sizeof(media), "%s/%s", temporary, name);
    run_ffmpeg(source, media, image);

    unsigned short port;
    int server = create_server(local, &port);
    pid_t child = fork();
    if (child < 0)
        fail("cannot start the local media server");
    if (child == 0)
        serve_once(server, media, name);
    close(server);

    char uri[1024], inner[2048];
    snprintf(uri, sizeof(uri), "http://%s:%u/%s", local, port, name);
    snprintf(inner, sizeof(inner), "<CurrentURI>%s</CurrentURI><CurrentURIMetaData></CurrentURIMetaData>", uri);
    (void)soap(host, control, "Pause", "");
    if (!soap(host, control, "SetAVTransportURI", inner) || !soap(host, control, "Play", "<Speed>1</Speed>")) {
        kill(child, SIGTERM);
        waitpid(child, NULL, 0);
        unlink(media);
        rmdir(temporary);
        fail("the projector rejected the DLNA playback request");
    }
    int status;
    if (waitpid(child, &status, 0) < 0 || !WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        unlink(media);
        rmdir(temporary);
        fail("the projector did not fetch the media");
    }
    unlink(media);
    rmdir(temporary);
    printf("Displaying %s on Hccast-079426 via DLNA\n", source);
    return EXIT_SUCCESS;
}
