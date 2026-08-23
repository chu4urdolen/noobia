#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L

#include "voice_stage.h"

#include "contact_book.h"
#include "file_transfer.h"
#include "network.h"
#include "protocol.h"

#include <errno.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <poll.h>
#include <unistd.h>

#define VOICE_REQUEST_TIMEOUT_MS 120000U

static volatile sig_atomic_t running = 1;
static volatile sig_atomic_t active_children = 0;
static network_socket active_listener = INVALID_NETWORK_SOCKET;
static void stop_worker(int signal_number)
{
    (void)signal_number;
    running = 0;
    if (active_listener != INVALID_NETWORK_SOCKET) network_close(active_listener);
    active_listener = INVALID_NETWORK_SOCKET;
}

static void reap_workers(int signal_number)
{
    int saved = errno;
    (void)signal_number;
    while (waitpid(-1, NULL, WNOHANG) > 0)
        if (active_children > 0) active_children--;
    errno = saved;
}

static void notify_systemd(const char *message)
{
    const char *path = getenv("NOTIFY_SOCKET");
    struct sockaddr_un address;
    int socket_fd;
    size_t length;
    if (path == NULL || *path == '\0' || strlen(path) >= sizeof(address.sun_path)) return;
    memset(&address, 0, sizeof(address));
    address.sun_family = AF_UNIX;
    snprintf(address.sun_path, sizeof(address.sun_path), "%s", path);
    length = strlen(path);
    if (address.sun_path[0] == '@') address.sun_path[0] = '\0';
    socket_fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (socket_fd < 0) return;
    (void)sendto(socket_fd, message, strlen(message), MSG_NOSIGNAL,
                 (struct sockaddr *)&address,
                 (socklen_t)(offsetof(struct sockaddr_un, sun_path) + length + 1));
    close(socket_fd);
}

static int make_output(const char *task, char path[1024])
{
    const char *suffix = !strcmp(task, "ENVELOPE") ? ".env" : ".wav";
    snprintf(path, 1024, "/tmp/rose-worker-output-XXXXXX%s", suffix);
    int fd = mkstemps(path, (int)strlen(suffix));
    if (fd < 0) return -1;
    close(fd);
    return 0;
}

static int execute_task(const char *task, const char *input, const char *output)
{
    if (!strcmp(task, "PIPER")) return voice_stage_piper(input, output);
    if (!strcmp(task, "SOX")) return voice_stage_sox(input, output);
    if (!strcmp(task, "ENVELOPE")) return voice_stage_envelope(input, output);
    return -1;
}

static void handle(network_socket socket, const contact_book *contacts)
{
    const contact *sender = NULL;
    char line[512], task[32], digest[65], input[1024] = "", output[1024] = "";
    unsigned long long size;
    char name[COUNCIL_FILE_NAME], output_digest[65];
    const char *input_name;
    uint64_t output_size;
    if (protocol_accept_identity(socket, contacts, CONTACT_AI, &sender) != 0) return;
    (void)sender;
    if (network_read_line(socket, line, sizeof(line)) < 0) return;
    if (!strcmp(line, "PING")) { (void)network_send(socket, "PONG\n"); return; }
    if (sscanf(line, "VOICE %31s %llu %64s", task, &size, digest) != 3 ||
        size > 67108864ULL || (strcmp(task, "PIPER") && strcmp(task, "SOX") &&
                              strcmp(task, "ENVELOPE"))) {
        (void)network_send(socket, "ERROR TASK\n"); return;
    }
    input_name = !strcmp(task, "PIPER") ? "rose-worker-input.txt" : "rose-worker-input.wav";
    if (network_send(socket, "READY\n") != 0 ||
        file_transfer_receive_stream(socket, "/tmp", input_name,
                                     (uint64_t)size, digest, input, sizeof(input)) != 0 ||
        make_output(task, output) != 0 || execute_task(task, input, output) != 0 ||
        file_transfer_describe(output, name, &output_size, output_digest) != 0) {
        (void)network_send(socket, "ERROR EXECUTION\n"); goto cleanup;
    }
    snprintf(line, sizeof(line), "RESULT %llu %s\n", (unsigned long long)output_size,
             output_digest);
    if (network_send(socket, line) != 0 || network_read_line(socket, line, sizeof(line)) < 0 ||
        strcmp(line, "READY") != 0 || file_transfer_send_stream(socket, output) != 0)
        goto cleanup;
cleanup:
    if (*output) remove(output);
    if (*input) remove(input);
}

int main(int argc, char **argv)
{
    const char *name = NULL, *contacts_path = "/etc/noobia-council/contacts.json";
    contact_book contacts;
    const contact *self;
    char error[256] = "invalid local identity";
    network_socket listener;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--name") && i + 1 < argc) name = argv[++i];
        else if (!strcmp(argv[i], "--contacts") && i + 1 < argc) contacts_path = argv[++i];
        else { fprintf(stderr, "Usage: %s --name NAME [--contacts FILE]\n", argv[0]); return 2; }
    }
    if (!name || contact_book_load(contacts_path, &contacts, error, sizeof(error)) != 0 ||
        !(self = contact_book_find(&contacts, name)) || self->role != CONTACT_AI ||
        self->port > 64535) {
        fprintf(stderr, "worker configuration failed: %s\n", error);
        return 2;
    }
    signal(SIGINT, stop_worker); signal(SIGTERM, stop_worker); signal(SIGCHLD, reap_workers);
    if (network_start() != 0 ||
        (listener = network_listen("0.0.0.0", (uint16_t)(self->port + 1000))) == INVALID_NETWORK_SOCKET) {
        fprintf(stderr, "cannot listen on voice worker port\n"); return 1;
    }
    active_listener = listener;
    fprintf(stderr, "%s voice worker listening on %u\n", name, self->port + 1000);
    notify_systemd("READY=1\nSTATUS=Listening for authenticated voice tasks");
    while (running) {
        struct pollfd ready = {listener, POLLIN, 0};
        int poll_result = poll(&ready, 1, 5000);
        if (poll_result == 0) { notify_systemd("WATCHDOG=1"); continue; }
        if (poll_result < 0) { if (errno == EINTR) continue; break; }
        network_socket socket = accept(listener, NULL, NULL);
        if (socket == INVALID_NETWORK_SOCKET) { if (errno == EINTR) continue; break; }
        if (active_children >= 4) { network_close(socket); continue; }
        if (network_set_io_timeout(socket, VOICE_REQUEST_TIMEOUT_MS) != 0) {
            network_close(socket);
            continue;
        }
        sigset_t child_signal, previous_signals;
        sigemptyset(&child_signal);
        sigaddset(&child_signal, SIGCHLD);
        (void)sigprocmask(SIG_BLOCK, &child_signal, &previous_signals);
        pid_t child = fork();
        if (child < 0) {
            (void)sigprocmask(SIG_SETMASK, &previous_signals, NULL);
            network_close(socket);
            continue;
        }
        if (child == 0) {
            (void)sigprocmask(SIG_SETMASK, &previous_signals, NULL);
            network_close(listener);
            handle(socket, &contacts);
            network_close(socket);
            _exit(0);
        }
        active_children++;
        (void)sigprocmask(SIG_SETMASK, &previous_signals, NULL);
        network_close(socket);
    }
    notify_systemd("STOPPING=1");
    if (active_listener != INVALID_NETWORK_SOCKET) network_close(active_listener);
    active_listener = INVALID_NETWORK_SOCKET;
    network_stop(); return 0;
}
