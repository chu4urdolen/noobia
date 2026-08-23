#include "voice_remote.h"

#include "file_transfer.h"
#include "network.h"
#include "protocol.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define VOICE_CONNECT_TIMEOUT_MS 5000U
#define VOICE_IO_TIMEOUT_MS 120000U

static int destination_for_worker(const contact *worker, const contact *sender,
                                  contact *destination)
{
    *destination = *worker;
    if (worker->port > 64535) return -1;
    destination->port = (uint16_t)(worker->port + 1000);
    memcpy(destination->shared_key, sender->shared_key, sizeof(destination->shared_key));
    return 0;
}

int voice_remote_available(const contact *worker, const contact *sender)
{
    contact destination;
    char reply[64];
    if (destination_for_worker(worker, sender, &destination) != 0) return 0;
    return protocol_send_command_timeout(&destination, sender->name, "PING", reply,
                                         sizeof(reply), 3000U) == 0 &&
           strcmp(reply, "PONG") == 0;
}

int voice_remote_run(const contact *worker, const contact *sender, voice_task task,
                     const char *input_path, const char *output_path)
{
    static const char *names[] = {"PIPER", "SOX", "ENVELOPE"};
    contact destination;
    network_socket socket;
    char input_name[COUNCIL_FILE_NAME], digest[65], line[512], returned[1024];
    unsigned long long output_size;
    uint64_t input_size;
    char output_digest[65];
    if (task < VOICE_TASK_PIPER || task > VOICE_TASK_ENVELOPE ||
        destination_for_worker(worker, sender, &destination) != 0 ||
        file_transfer_describe(input_path, input_name, &input_size, digest) != 0 ||
        protocol_connect_identity_timeout(&destination, sender->name,
                                          VOICE_CONNECT_TIMEOUT_MS, &socket) != 0) return -1;
    if (network_set_io_timeout(socket, VOICE_IO_TIMEOUT_MS) != 0) {
        network_close(socket);
        return -1;
    }
    snprintf(line, sizeof(line), "VOICE %s %llu %s\n", names[task],
             (unsigned long long)input_size, digest);
    if (network_send(socket, line) || network_read_line(socket, line, sizeof(line)) < 0 ||
        strcmp(line, "READY") != 0 || file_transfer_send_stream(socket, input_path) != 0 ||
        network_read_line(socket, line, sizeof(line)) < 0 ||
        sscanf(line, "RESULT %llu %64s", &output_size, output_digest) != 2 ||
        output_size > 67108864ULL || network_send(socket, "READY\n") != 0) {
        network_close(socket);
        return -1;
    }
    int received = file_transfer_receive_stream(socket, "/tmp", "rose-voice-result",
                                                (uint64_t)output_size, output_digest,
                                                returned, sizeof(returned));
    network_close(socket);
    if (received != 0 || rename(returned, output_path) != 0) {
        if (received == 0) remove(returned);
        return -1;
    }
    return 0;
}
