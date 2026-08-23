#ifndef NOOBIA_NETWORK_H
#define NOOBIA_NETWORK_H
#include <stddef.h>
#include <stdint.h>
#ifdef _WIN32
#include <winsock2.h>
typedef SOCKET network_socket;
#define INVALID_NETWORK_SOCKET INVALID_SOCKET
#else
typedef int network_socket;
#define INVALID_NETWORK_SOCKET (-1)
#endif
int network_start(void);
void network_stop(void);
void network_close(network_socket socket);
int network_connect(const char *host, uint16_t port, network_socket *result);
int network_connect_timeout(const char *host, uint16_t port, unsigned int timeout_ms,
                            network_socket *result);
int network_set_io_timeout(network_socket socket, unsigned int timeout_ms);
network_socket network_listen(const char *address, uint16_t port);
int network_send(network_socket socket, const char *data);
int network_send_bytes(network_socket socket, const void *data, size_t size);
int network_read_bytes(network_socket socket, void *data, size_t size);
int network_read_line(network_socket socket, char *buffer, size_t capacity);
#endif
