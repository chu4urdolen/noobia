#ifndef NOOBIA_PROTOCOL_H
#define NOOBIA_PROTOCOL_H
#include "contact_book.h"
#include "network.h"
#define COUNCIL_MESSAGE_LENGTH 8192
int protocol_accept_identity(network_socket socket, const contact_book *book,
                             contact_role expected_role,
                             const contact **identity);
int protocol_connect_identity(const contact *destination, const char *local_name,
                              network_socket *socket);
int protocol_send_command(const contact *destination, const char *local_name,
                          const char *command, char *reply, size_t reply_size);
#endif

