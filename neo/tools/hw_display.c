#define _GNU_SOURCE
#include "hw_display.h"
#include <fcntl.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static NoobReply reply;
static pid_t worker = -1;
static bool thread;
static int last_exit = -1;
static char active_image[192];
static int32_t active_interval;

void hw_display_bind(NoobReply output) { reply = output; }

static void reap(void) {
  int status;
  if (worker > 0 && waitpid(worker, &status, WNOHANG) == worker) {
    last_exit = WIFEXITED(status) ? WEXITSTATUS(status) : 128;
    worker = -1;
  }
}

static void stop(void) {
  if (worker <= 0) return;
  kill(-worker, SIGTERM);
  for (unsigned i = 0; i < 20; ++i) {
    reap();
    if (worker <= 0) return;
    struct timespec pause = {.tv_nsec = 10000000};
    nanosleep(&pause, NULL);
  }
  kill(-worker, SIGKILL);
  (void)waitpid(worker, NULL, 0);
  worker = -1;
}

void hw_display_call(int client, unsigned id, const char *name,
                      const NoobNativeArguments *args) {
  reap();
  if (!strcmp(name, "DISPLAY_STATUS")) {
    char result[128];
    snprintf(result, sizeof(result), "value=%u running=%u channel_busy=%u type=%s exit=%d",
             worker > 0, worker > 0, worker > 0, thread ? "thread" : "sequence", last_exit);
    reply(client, id, "OK", result); return;
  }
  if (!strcmp(name, "DISPLAY_STOP")) {
    stop(); reply(client, id, "OK", "value=0 stopped=1 channel_busy=0"); return;
  }
  bool start = !strcmp(name, "DISPLAY_START");
  if (start && (args->numbers[0] < 1000 || args->numbers[0] > 60000)) {
    reply(client, id, "ERR BAD_ARGUMENTS", "interval_ms must be 1000..60000"); return;
  }
  if (worker > 0 && start && thread &&
      (strcmp(active_image, args->ascii) || active_interval != args->numbers[0])) stop();
  if (worker > 0) {
    /* Repeated VM startup attempts do not restart an active thread. */
    if (start && thread) reply(client, id, "OK", "value=1 already_running=1");
    else reply(client, id, "ERR BUSY", "display channel occupied");
    return;
  }
  const char *operation = start ? "thread" :
      !strcmp(name, "IMAGE_FORMAT") ? "format" :
      !strcmp(name, "OLED_DRAW") ? "image" : "text";
  char interval[16];
  snprintf(interval, sizeof(interval), "%d", args->numbers[0]);
  const char *directory = getenv("NOOB_ESP_DIR");
  if (!directory) directory = "/esp";
  char log_path[256];
  if (snprintf(log_path, sizeof(log_path), "%s/.display.log", directory) >= (int)sizeof(log_path)) {
    reply(client, id, "ERR IO", "display log path too long"); return;
  }
  int log = open(log_path, O_WRONLY | O_APPEND | O_CREAT | O_CLOEXEC | O_NOFOLLOW, 0600);
  if (log < 0) { reply(client, id, "ERR IO", "display log unavailable"); return; }
  worker = fork();
  if (worker == 0) {
    setpgid(0, 0);
    close(client);
    dup2(log, STDOUT_FILENO); dup2(log, STDERR_FILENO); close(log);
    const char *tool = getenv("NOOB_DISPLAY_TOOL");
    if (!tool) tool = "/usr/local/bin/noob-display";
    execl(tool, tool, operation, args->ascii, start ? interval : NULL, (char *)NULL);
    _exit(127);
  }
  close(log);
  if (worker < 0) { reply(client, id, "ERR IO", "display worker failed"); return; }
  (void)setpgid(worker, worker);
  thread = start;
  snprintf(active_image, sizeof(active_image), "%s", args->ascii);
  active_interval = args->numbers[0];
  last_exit = -1;
  reply(client, id, "OK", "value=1 started=1 async=1 channel_busy=1");
}
