#ifndef NOOBIA_TRANSCRIPT_H
#define NOOBIA_TRANSCRIPT_H
#include "network.h"
#include <stddef.h>
int transcript_append(const char *path, const char *speaker,
                      const char *event, const char *message);
int transcript_stream_since(const char *path, long offset,
                            network_socket socket, long *next_offset);
int transcript_stream_context(const char *path, const char *participant,
                              network_socket socket);
int transcript_last_speaker(const char *path, char *speaker,
                            size_t speaker_size);
#endif

