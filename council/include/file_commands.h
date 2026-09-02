#ifndef NOOBIA_FILE_COMMANDS_H
#define NOOBIA_FILE_COMMANDS_H
#include "contact_book.h"
#include "network.h"
#include "service_config.h"
int file_command_handle(const char *line, network_socket socket,
                        const contact *sender, const service_config *config,
                        const contact_book *contacts, int sender_has_turn);
#endif
