#define _GNU_SOURCE
#include <arpa/inet.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

/* Deterministic bytes include NULs and span multiple SD_READ chunks. */
int main(int argc, char **argv) {
  unsigned char bytes[769];
  for (size_t i = 0; i < sizeof(bytes); ++i) bytes[i] = (unsigned char)i;
  if (argc == 2 && !strcmp(argv[1], "--emit")) {
    return fwrite(bytes, 1, sizeof(bytes), stdout) == sizeof(bytes) ? 0 : 1;
  }
  int server = socket(AF_INET, SOCK_STREAM, 0);
  struct sockaddr_in address = {.sin_family = AF_INET,
      .sin_addr.s_addr = htonl(INADDR_LOOPBACK)};
  if (bind(server, (struct sockaddr *)&address, sizeof(address)) || listen(server, 4)) return 1;
  socklen_t length = sizeof(address);
  if (getsockname(server, (struct sockaddr *)&address, &length)) return 1;
  printf("%u\n", ntohs(address.sin_port)); fflush(stdout);
  for (;;) {
    int client = accept(server, NULL, NULL);
    if (client < 0) return 1;
    FILE *stream = fdopen(client, "r+");
    if (!stream) return 1;
    setvbuf(stream, NULL, _IONBF, 0);
    char request[1024];
    while (fgets(request, sizeof(request), stream)) {
      char id[64]; unsigned offset, count;
      if (sscanf(request, "NRP/1 %63s CALL_MIXED SD_READ %u %u", id, &offset, &count) != 3 ||
          offset > sizeof(bytes) || count > 512) return 1;
      if (count > sizeof(bytes) - offset) count = sizeof(bytes) - offset;
      fprintf(stream, "NRP/1 %s OK value=%u detail=size=%zu eof=%u data=",
              id, count, sizeof(bytes), offset + count == sizeof(bytes));
      for (unsigned i = 0; i < count; ++i) fprintf(stream, "%02x", bytes[offset+i]);
      fprintf(stream, "\n");
    }
    fclose(stream);
  }
}
