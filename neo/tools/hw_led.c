#include <errno.h>
#include <fcntl.h>
#include <linux/gpio.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include "hw_led.h"
#include "hw_led_config.h"

#define LED_COUNT (sizeof(noob_led_pins) / sizeof(noob_led_pins[0]))
static int handles[LED_COUNT]; /* fd + 1; zero means unclaimed. */
static NoobReply reply;
void hw_led_bind(NoobReply callback) { reply = callback; }
static int index_of(int pin) {
  for (unsigned i = 0; i < LED_COUNT; ++i)
    if (noob_led_pins[i].pin == pin) return (int)i;
  return -1;
}
static int claim(unsigned i) {
  if (handles[i]) return handles[i] - 1;
  int chip = open(NOOB_LED_CHIP, O_RDONLY | O_CLOEXEC);
  if (chip < 0) return -1;
  struct gpio_v2_line_request request = {0};
  request.offsets[0] = noob_led_pins[i].line;
  request.num_lines = 1;
  request.config.flags = GPIO_V2_LINE_FLAG_OUTPUT;
  /* Claim atomically as LOW. */
  request.config.num_attrs = 1;
  request.config.attrs[0].attr.id = GPIO_V2_LINE_ATTR_ID_OUTPUT_VALUES;
  request.config.attrs[0].mask = 1;
  snprintf(request.consumer, sizeof(request.consumer), "noob-led-%d", noob_led_pins[i].pin);
  int rc = ioctl(chip, GPIO_V2_GET_LINE_IOCTL, &request);
  int saved = errno;
  close(chip);
  errno = saved;
  if (rc < 0) return -1;
  handles[i] = request.fd + 1;
  return request.fd;
}
int hw_led_boot(void) {
  int i = index_of(NOOB_LED_BOOT_PIN);
  if (i < 0) { errno = EINVAL; return -1; }
  return claim((unsigned)i) < 0 ? -1 : 0;
}
void hw_led_call(int client, unsigned id, const char *name,
                 const NoobNativeArguments *args) {
  int set = !strcmp(name, "LED_SET");
  int i = args->count ? index_of(args->numbers[0]) : -1;
  if (args->count != (unsigned)(set ? 2 : 1) || args->ascii[0] || i < 0 ||
      (set && args->numbers[1] != 0 && args->numbers[1] != 1)) {
    reply(client, id, "ERR BAD_ARGUMENTS", "LED_SET physical_pin 0|1; LED_STATUS physical_pin");
    return;
  }
  /* Reading an unused pin must not change it. */
  if (!set && !handles[i]) {
    reply(client, id, "OK", "claimed=0 state=unknown"); return;
  }
  int fd = claim((unsigned)i);
  struct gpio_v2_line_values values = {.mask = 1};
  if (set) values.bits = (unsigned)args->numbers[1];
  if (fd < 0 || ioctl(fd, set ? GPIO_V2_LINE_SET_VALUES_IOCTL : GPIO_V2_LINE_GET_VALUES_IOCTL,
                      &values) < 0) {
    char error[160];
    snprintf(error, sizeof(error), "pin=%d errno=%d %s", args->numbers[0], errno, strerror(errno));
    reply(client, id, "ERR GPIO", error); return;
  }
  char result[96];
  snprintf(result, sizeof(result), "pin=%d claimed=1 value=%u", args->numbers[0], (unsigned)(values.bits & 1));
  reply(client, id, "OK", result);
}
