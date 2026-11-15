#ifndef NOOBIA_FILE_TRANSFER_H
#define NOOBIA_FILE_TRANSFER_H
#include "contact_book.h"
#include "network.h"
#include <stddef.h>
#include <stdint.h>
#define COUNCIL_FILE_NAME 128
int file_transfer_name_is_safe(const char *name);
int file_transfer_describe(const char *path, char name[COUNCIL_FILE_NAME],
                           uint64_t *size, char digest[65]);
int file_transfer_send_stream(network_socket socket, const char *path);
int file_transfer_receive_stream(network_socket socket, const char *directory,
                                 const char *name, uint64_t size,
                                 const char *digest, char *stored_path,
                                 size_t stored_path_size);
int file_transfer_forward(const contact *destination, const char *local_name,
                          const char *sender, const char *path,
                          const char *name, uint64_t size,
                          const char *digest, char *reply,
                          size_t reply_size);
#endif
