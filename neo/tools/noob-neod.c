#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <netinet/in.h>
#include <signal.h>
#include <poll.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include "noob_native_registry.h"
#include "hw_display.h"

#define REQUEST_BYTES 512
#define REPLY_BYTES 768
#define IR_QUEUE_SIZE 16

static pid_t scan_pid = -1;
static int scan_output = -1;
static const char *ir_tool = "ir-keytable";
static char scan_line[256];
static size_t scan_line_used;
static uint32_t ir_queue[IR_QUEUE_SIZE];
static size_t ir_head;
static size_t ir_count;
static pid_t file_pid = -1;
static int file_exit = -1;
static const char *file_tool = "/usr/local/bin/noob-files";
static const char *vm_directory = "/vm";
static const char *job_directory = "/esp";

static void drain_scan(void);

static void queue_scancode(const char *line) {
  const char *field = strstr(line, "scancode = ");
  if (!field) return;
  char *end = NULL;
  unsigned long value = strtoul(field + 11, &end, 0);
  if (end == field + 11) return;
  if (ir_count == IR_QUEUE_SIZE) {
    ir_head = (ir_head + 1) % IR_QUEUE_SIZE;
    --ir_count;
  }
  ir_queue[(ir_head + ir_count) % IR_QUEUE_SIZE] = (uint32_t)value;
  ++ir_count;
}

static void collect_scancodes(const char *bytes, size_t length) {
  for (size_t i = 0; i < length; ++i) {
    char c = bytes[i];
    if (c == '\n' || c == '\r') {
      scan_line[scan_line_used] = '\0';
      queue_scancode(scan_line);
      scan_line_used = 0;
    } else if (scan_line_used + 1 < sizeof(scan_line) && c >= 32 && c < 127) {
      scan_line[scan_line_used++] = c;
    } else if (scan_line_used + 1 >= sizeof(scan_line)) {
      scan_line_used = 0;
    }
  }
}

static bool path_exists(const char *path) {
  struct stat info;
  return stat(path, &info) == 0;
}

static void stop_scan(void) {
  if (scan_pid > 0) {
    kill(scan_pid, SIGTERM);
    for (unsigned i = 0; i < 20; ++i) {
      if (waitpid(scan_pid, NULL, WNOHANG) != 0) break;
      struct timespec delay = {.tv_nsec = 10000000};
      nanosleep(&delay, NULL);
    }
    if (waitpid(scan_pid, NULL, WNOHANG) == 0) {
      kill(scan_pid, SIGKILL);
      (void)waitpid(scan_pid, NULL, 0);
    }
  }
  if (scan_output >= 0) close(scan_output);
  scan_pid = -1;
  scan_output = -1;
  scan_line_used = 0;
  ir_head = 0;
  ir_count = 0;
}

static void drain_scan(void) {
  if (scan_output >= 0) {
    char bytes[512];
    for (unsigned i = 0; i < 8; ++i) {
      ssize_t got = read(scan_output, bytes, sizeof(bytes));
      if (got <= 0) break;
      collect_scancodes(bytes, (size_t)got);
    }
  }
  if (scan_pid > 0 && waitpid(scan_pid, NULL, WNOHANG) == scan_pid) {
    scan_pid = -1;
    if (scan_output >= 0) close(scan_output);
    scan_output = -1;
  }
}

static bool ir_ready(void) {
  return path_exists("/sys/class/rc/rc0") && access(ir_tool, X_OK) == 0;
}

static void respond(int client, unsigned id, const char *status,
                    const char *payload) {
  char reply[REPLY_BYTES];
  int n = snprintf(reply, sizeof(reply), "NRP/1 %u %s%s%s\n", id, status,
                   payload && *payload ? " " : "", payload ? payload : "");
  if (n > 0 && (size_t)n < sizeof(reply)) {
    size_t sent = 0;
    while (sent < (size_t)n) {
      ssize_t wrote = send(client, reply + sent, (size_t)n - sent, MSG_NOSIGNAL);
      if (wrote <= 0) break;
      sent += (size_t)wrote;
    }
  }
}

static bool unhex(const char *hex, char *out, size_t capacity) {
  size_t length = strlen(hex);
  if (!length || length % 2 || length / 2 >= capacity) return false;
  for (size_t i = 0; i < length; i += 2) {
    unsigned char bytes[2] = {(unsigned char)hex[i], (unsigned char)hex[i + 1]};
    int value = 0;
    for (unsigned j = 0; j < 2; ++j) {
      int n = bytes[j] >= '0' && bytes[j] <= '9' ? bytes[j] - '0' :
              bytes[j] >= 'a' && bytes[j] <= 'f' ? bytes[j] - 'a' + 10 :
              bytes[j] >= 'A' && bytes[j] <= 'F' ? bytes[j] - 'A' + 10 : -1;
      if (n < 0) return false;
      value = value * 16 + n;
    }
    if (value < 32 || value > 126) return false;
    out[i / 2] = (char)value;
  }
  out[length / 2] = '\0';
  return true;
}

static bool basename_ok(const char *name) {
  if (!*name || *name == '.' || strstr(name, "..")) return false;
  for (const char *p = name; *p; ++p)
    if (!((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') ||
          (*p >= '0' && *p <= '9') || *p == '_' || *p == '-' || *p == '.'))
      return false;
  return true;
}

static void reap_file(void) {
  int status;
  if (file_pid > 0 && waitpid(file_pid, &status, WNOHANG) == file_pid) {
    file_exit = WIFEXITED(status) ? WEXITSTATUS(status) : 128;
    file_pid = -1;
  }
}

static void file_command(int client, unsigned id, const char *command,
                         const char *arguments) {
  reap_file();
  if (strcmp(command, "FILE_STATUS") == 0 && !*arguments) {
    char result[96];
    snprintf(result, sizeof(result), "value=%d running=%u exit=%d",
             file_pid > 0 ? 1 : 0, file_pid > 0 ? 1u : 0u, file_exit);
    respond(client, id, "OK", result);
    return;
  }
  char name[192];
  if (strcmp(command, "VM_READ") == 0) {
    unsigned offset;
    char hex[384], extra;
    if (sscanf(arguments, "%u %383s %c", &offset, hex, &extra) != 2 ||
        !unhex(hex, name, sizeof(name)) || !basename_ok(name)) {
      respond(client, id, "ERR BAD_REQUEST", "expected offset and hex VM basename"); return;
    }
    size_t length = strlen(name);
    if (length < 5 || strcmp(name + length - 4, ".nvm") != 0) {
      respond(client, id, "ERR BAD_PATH", "VM file must end in .nvm"); return;
    }
    int directory = open(vm_directory, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    int fd = directory < 0 ? -1 : openat(directory, name, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (directory >= 0) close(directory);
    struct stat info;
    if (fd < 0 || fstat(fd, &info) || !S_ISREG(info.st_mode) ||
        info.st_size < 1 || info.st_size > 1024 || offset > (unsigned)info.st_size) {
      if (fd >= 0) close(fd);
      respond(client, id, "ERR VM_FILE", "VM unavailable or invalid size"); return;
    }
    unsigned char bytes[128];
    ssize_t got = pread(fd, bytes, sizeof(bytes), offset);
    close(fd);
    if (got < 0) { respond(client, id, "ERR IO", "VM read failed"); return; }
    char payload[384];
    int used = snprintf(payload, sizeof(payload), "value=%zd size=%ld eof=%u data=",
                        got, (long)info.st_size, offset + (unsigned)got == (unsigned)info.st_size);
    for (ssize_t i = 0; i < got; ++i) {
      snprintf(payload + used, sizeof(payload) - (size_t)used, "%02x", bytes[i]); used += 2;
    }
    respond(client, id, "OK", payload);
    return;
  }
  bool fetch = strcmp(command, "FILE_DOWNLOAD") == 0;
  bool play = strcmp(command, "AUDIO_PLAY") == 0;
  if ((!fetch && !play) || !unhex(arguments, name, sizeof(name)) ||
      (fetch && (*name != '/' || strstr(name, "..") || strchr(name, '\\'))) ||
      (play && !basename_ok(name))) {
    respond(client, id, "ERR BAD_REQUEST", "invalid file operation or path"); return;
  }
  if (file_pid > 0) { respond(client, id, "ERR BUSY", "file or audio job running"); return; }
  char log_path[PATH_MAX];
  snprintf(log_path, sizeof(log_path), "%s/.job.log", job_directory);
  int log = open(log_path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC | O_NOFOLLOW, 0600);
  if (log < 0) { respond(client, id, "ERR IO", "job log unavailable"); return; }
  file_pid = fork();
  if (file_pid == 0) {
    close(client);
    dup2(log, STDOUT_FILENO); dup2(log, STDERR_FILENO); close(log);
    execl(file_tool, file_tool, fetch ? "fetch" : "play", name, (char *)NULL);
    _exit(127);
  }
  close(log);
  if (file_pid < 0) { respond(client, id, "ERR IO", "job start failed"); return; }
  file_exit = -1;
  respond(client, id, "OK", "value=1 started=1 async=1");
}

/* Hardware adapters retain the legacy wire forms for existing ESP images. */
static void hw_command(int client, unsigned id, const char *command,
                       const char *arguments) {
  if (strcmp(command, "FILE_DOWNLOAD") == 0 || strcmp(command, "FILE_STATUS") == 0 ||
             strcmp(command, "AUDIO_PLAY") == 0 || strcmp(command, "VM_READ") == 0) {
    file_command(client, id, command, arguments);
  } else if (*arguments) {
    respond(client, id, "ERR BAD_REQUEST", "unexpected arguments");
  } else if (strcmp(command, "PING") == 0) {
    respond(client, id, "OK", "PONG");
  } else if (strcmp(command, "CAPS") == 0) {
    respond(client, id, "OK", "name=Neo functions=IR_STATUS,IR_SCAN_START,IR_SCAN_STOP,IR_SCAN_READ,FILE_DOWNLOAD,FILE_STATUS,VM_READ,AUDIO_PLAY");
  } else if (strcmp(command, "IR_STATUS") == 0) {
    if (!ir_ready()) {
      respond(client, id, "ERR IR_UNAVAILABLE", "no rc0 device or ir-keytable; enable the HAT IR driver first");
    } else {
      char state[64];
      snprintf(state, sizeof(state), "value=%u ready=1 scanning=%u",
               scan_pid > 0 ? 1u : 0u, scan_pid > 0 ? 1u : 0u);
      respond(client, id, "OK", state);
    }
  } else if (strcmp(command, "IR_SCAN_START") == 0) {
    if (!ir_ready()) {
      respond(client, id, "ERR IR_UNAVAILABLE", "no rc0 device or ir-keytable; enable the HAT IR driver first");
    } else if (scan_pid > 0) {
      respond(client, id, "OK", "value=1 already_running=1");
    } else {
      int output[2];
      if (pipe2(output, O_CLOEXEC) != 0) {
        respond(client, id, "ERR IO", "cannot create scanner pipe");
      } else {
        scan_pid = fork();
        if (scan_pid == 0) {
          close(client);
          dup2(output[1], STDOUT_FILENO);
          dup2(output[1], STDERR_FILENO);
          close(output[0]);
          close(output[1]);
          /* Deliver each event immediately, not after a full stdout buffer. */
          execl("/usr/bin/stdbuf", "stdbuf", "-oL", "-eL", ir_tool,
                "-s", "rc0", "-t", (char *)NULL);
          _exit(127);
        }
        close(output[1]);
        if (scan_pid < 0) {
          close(output[0]);
          scan_pid = -1;
          respond(client, id, "ERR IO", "cannot start ir-keytable");
        } else {
          scan_output = output[0];
          int flags = fcntl(scan_output, F_GETFL, 0);
          if (flags >= 0) fcntl(scan_output, F_SETFL, flags | O_NONBLOCK);
          respond(client, id, "OK", "value=1 started=1");
        }
      }
    }
  } else if (strcmp(command, "IR_SCAN_STOP") == 0) {
    stop_scan();
    respond(client, id, "OK", "value=1 stopped=1");
  } else if (strcmp(command, "IR_SCAN_READ") == 0) {
    if (scan_pid <= 0 || scan_output < 0) {
      respond(client, id, "ERR NOT_RUNNING", "start IR_SCAN first");
    } else {
      char raw[480];
      ssize_t got = read(scan_output, raw, sizeof(raw) - 1);
      if (got < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
        respond(client, id, "ERR IO", "scanner read failed");
      } else {
        if (got < 0) got = 0;
        raw[got] = '\0';
        collect_scancodes(raw, (size_t)got);
        uint32_t code = 0;
        if (ir_count) {
          code = ir_queue[ir_head];
          ir_head = (ir_head + 1) % IR_QUEUE_SIZE;
          --ir_count;
        }
        char result[96];
        snprintf(result, sizeof(result), "value=%d scancode=0x%08x queued=%zu",
                 (int32_t)code, (unsigned)code, ir_count);
        respond(client, id, "OK", result);
      }
    }
  } else {
    respond(client, id, "ERR UNKNOWN_COMMAND", command);
  }
}

static void native_adapter(int client, unsigned id, const char *name,
                            const NoobNativeArguments *args) {
  char encoded[sizeof(args->ascii) * 2];
  const char *digits = "0123456789abcdef";
  size_t length = strlen(args->ascii);
  for (size_t i = 0; i < length; ++i) {
    unsigned char c = (unsigned char)args->ascii[i];
    encoded[i*2] = digits[c >> 4];
    encoded[i*2+1] = digits[c & 15];
  }
  encoded[length*2] = '\0';
  char arguments[432];
  if (args->count) {
    if (args->numbers[0] < 0) {
      respond(client, id, "ERR BAD_ARGUMENTS", "offset must be nonnegative"); return;
    }
    snprintf(arguments, sizeof(arguments), "%d %s", args->numbers[0], encoded);
  } else {
    snprintf(arguments, sizeof(arguments), "%s", encoded);
  }
  hw_command(client, id, name, arguments);
}

static const NoobNativeEntry natives[] = {
  {"IR_STATUS", 0, 0, native_adapter},
  {"IR_SCAN_START", 0, 0, native_adapter},
  {"IR_SCAN_STOP", 0, 0, native_adapter},
  {"IR_SCAN_READ", 0, 0, native_adapter},
  {"FILE_DOWNLOAD", 0, 1, native_adapter},
  {"FILE_STATUS", 0, 0, native_adapter},
  {"VM_READ", 1, 1, native_adapter},
  {"AUDIO_PLAY", 0, 1, native_adapter},
  {"IMAGE_FORMAT", 0, 1, hw_display_call},
  {"OLED_DRAW", 0, 1, hw_display_call},
  {"OLED_TEXT", 0, 1, hw_display_call},
  {"DISPLAY_START", 1, 1, hw_display_call},
  {"DISPLAY_STOP", 0, 0, hw_display_call},
  {"DISPLAY_STATUS", 0, 0, hw_display_call},
};
#define NATIVE_COUNT (sizeof(natives) / sizeof(natives[0]))

/* Transport -> protocol -> registry -> native service -> reply. */
static void handle(int client) {
  char request[REQUEST_BYTES];
  size_t used = 0;
  bool complete = false;
  while (used + 1 < sizeof(request)) {
    ssize_t n = recv(client, request + used, 1, 0);
    if (n <= 0) return;
    if (request[used] == '\n') { complete = true; break; }
    if (request[used] == '\0') return;
    ++used;
  }
  if (!complete) { respond(client, 0, "ERR BAD_REQUEST", "request too long"); return; }
  request[used] = '\0';
  drain_scan();
  unsigned id = 0;
  char command[48] = {0};
  int offset = 0;
  if (sscanf(request, "NRP/1 %u %47s %n", &id, command, &offset) != 2 || !offset) {
    respond(client, id, "ERR BAD_REQUEST", "expected NRP/1 id command"); return;
  }
  const char *arguments = request + offset;
  if (!strcmp(command, "PING") && !*arguments) {
    respond(client, id, "OK", "PONG"); return;
  }
  if (!strcmp(command, "CAPS") && !*arguments) {
    char caps[480] = "name=Neo native_calls=CALL,CALL_MIXED functions=";
    for (unsigned i = 0; i < NATIVE_COUNT; ++i) {
      if (i) strcat(caps, ",");
      strcat(caps, natives[i].name);
    }
    respond(client, id, "OK", caps); return;
  }
  if (!strcmp(command, "CALL") || !strcmp(command, "CALL_MIXED")) {
    char name[48];
    int start = 0;
    if (sscanf(arguments, "%47s %n", name, &start) != 1 || !start) {
      respond(client, id, "ERR BAD_REQUEST", "missing native name"); return;
    }
    const NoobNativeEntry *entry = noob_native_find(natives, NATIVE_COUNT, name);
    NoobNativeArguments parsed;
    if (!entry) { respond(client, id, "ERR UNKNOWN_FUNCTION", name); return; }
    if (!noob_native_parse(arguments + start, !strcmp(command, "CALL_MIXED"), &parsed) ||
        parsed.count != entry->numbers || (!!parsed.ascii[0] != entry->text)) {
      respond(client, id, "ERR BAD_ARGUMENTS", "wrong numeric/ASCII arguments"); return;
    }
    entry->call(client, id, entry->name, &parsed); return;
  }
  /* Compatibility is bounded to registered names, never shell commands. */
  if (noob_native_find(natives, NATIVE_COUNT, command))
    hw_command(client, id, command, arguments);
  else
    respond(client, id, "ERR UNKNOWN_COMMAND", command);
}

int main(void) {
  hw_display_bind(respond);
  const char *bind_ip = getenv("NOOB_NEOD_BIND");
  const char *port_text = getenv("NOOB_NEOD_PORT");
  const char *tool = getenv("NOOB_NEOD_IR_TOOL");
  if (!bind_ip || !*bind_ip) bind_ip = "127.0.0.1";
  if (port_text && *port_text) {
    char *end = NULL;
    long port = strtol(port_text, &end, 10);
    if (!end || *end || port < 1 || port > 65535) return 2;
  }
  unsigned port = port_text && *port_text ? (unsigned)strtoul(port_text, NULL, 10) : 4243;
  ir_tool = tool && *tool ? tool : "/usr/bin/ir-keytable";
  const char *vm_path = getenv("NOOB_VM_DIR");
  const char *job_path = getenv("NOOB_ESP_DIR");
  if (vm_path && *vm_path) vm_directory = vm_path;
  if (job_path && *job_path) job_directory = job_path;
  signal(SIGPIPE, SIG_IGN);

  for (;;) {
    int server = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (server < 0) return 1;
    int reuse = 1;
    setsockopt(server, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
    struct sockaddr_in address = {.sin_family = AF_INET, .sin_port = htons((uint16_t)port)};
    if (inet_pton(AF_INET, bind_ip, &address.sin_addr) != 1) return 2;
    if (bind(server, (struct sockaddr *)&address, sizeof(address)) != 0 || listen(server, 4) != 0) {
      close(server);
      if (errno == EADDRNOTAVAIL || errno == EADDRINUSE) {
        struct timespec delay = {.tv_sec = 2, .tv_nsec = 0};
        nanosleep(&delay, NULL);
        continue;
      }
      return 1;
    }
    for (;;) {
      drain_scan();
      reap_file();
      struct pollfd ready = {.fd = server, .events = POLLIN};
      int polled = poll(&ready, 1, 100);
      if (polled == 0 || (polled < 0 && errno == EINTR)) continue;
      if (polled < 0) break;
      int client = accept4(server, NULL, NULL, SOCK_CLOEXEC);
      if (client < 0) {
        if (errno == EINTR) continue;
        break;
      }
      struct timeval timeout = {.tv_sec = 2, .tv_usec = 0};
      setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
      setsockopt(client, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
      handle(client);
      close(client);
    }
    close(server);
  }
}
