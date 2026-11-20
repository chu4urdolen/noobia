#include <assert.h>
#include <errno.h>
#include <linux/gpio.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include "../tools/hw_led.h"

static unsigned requests, values[300], last_line;
static int fail_claim;
static char result[192], status[48];
int __wrap_open(const char *path, int flags, ...) {
  (void)flags; assert(!strcmp(path, "/dev/gpiochip0")); return 999;
}
int __wrap_close(int fd) { assert(fd == 999); return 0; }
int __wrap_ioctl(int fd, unsigned long op, ...) {
  va_list ap; va_start(ap, op); void *p = va_arg(ap, void *); va_end(ap);
  if (op == GPIO_V2_GET_LINE_IOCTL) {
    assert(fd == 999);
    struct gpio_v2_line_request *r = p;
    assert(r->num_lines == 1 && r->config.flags == GPIO_V2_LINE_FLAG_OUTPUT);
    assert(r->config.attrs[0].attr.id == GPIO_V2_LINE_ATTR_ID_OUTPUT_VALUES);
    assert(r->config.attrs[0].mask == 1 && r->config.attrs[0].attr.values == 0);
    if (fail_claim) { errno = EBUSY; return -1; }
    last_line = r->offsets[0]; ++requests;
    r->fd = 1000 + (int)last_line; values[last_line] = 0;
  } else {
    assert(fd >= 1000 && fd < 1300);
    struct gpio_v2_line_values *v = p; assert(v->mask == 1);
    if (op == GPIO_V2_LINE_SET_VALUES_IOCTL) values[fd - 1000] = v->bits;
    else { assert(op == GPIO_V2_LINE_GET_VALUES_IOCTL); v->bits = values[fd - 1000]; }
  }
  return 0;
}
static void respond(int client, unsigned id, const char *s, const char *text) {
  (void)client; (void)id;
  snprintf(result, sizeof(result), "%s", text); snprintf(status, sizeof(status), "%s", s);
}
static void call(const char *name, int pin, int state) {
  NoobNativeArguments args = {.numbers = {pin, state}, .count = !strcmp(name, "LED_SET") ? 2 : 1};
  hw_led_call(0, 0, name, &args);
}
int main(void) {
  hw_led_bind(respond);
  assert(hw_led_boot() == 0 && requests == 1 && last_line == 66 && values[66] == 0);
  call("LED_STATUS", 7, 0); assert(requests == 1 && strstr(result, "claimed=0"));
  call("LED_SET", 3, 1); assert(!strcmp(status, "ERR BAD_ARGUMENTS") && requests == 1);
  call("LED_SET", 23, 2); assert(!strcmp(status, "ERR BAD_ARGUMENTS") && values[66] == 0);
  fail_claim = 1; call("LED_SET", 7, 1); assert(!strcmp(status, "ERR GPIO")); fail_claim = 0;
  const int pins[] = {7, 11, 12, 13, 15, 19, 21, 22, 23, 24};
  for (unsigned i = 0; i < 10; ++i) {
    call("LED_SET", pins[i], 1); assert(!strcmp(status, "OK"));
    call("LED_STATUS", pins[i], 0); assert(strstr(result, "value=1"));
    call("LED_SET", pins[i], 0); assert(strstr(result, "value=0"));
  }
  assert(requests == 10);
  call("LED_SET", 23, 1); call("LED_SET", 24, 0); assert(values[66] == 1 && values[67] == 0);
  puts("LED boot LOW, individual pins, validation, busy errors and isolation passed");
}
