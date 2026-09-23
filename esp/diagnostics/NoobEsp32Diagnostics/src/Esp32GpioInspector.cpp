#include "Esp32GpioInspector.h"

#include <driver/gpio.h>

namespace {
constexpr uint8_t MAX_GPIO = 48;
const char *reservations[MAX_GPIO + 1] = {};
bool pullAllowed[MAX_GPIO + 1] = {};
uint8_t configuredHighest = MAX_GPIO;

bool inRange(int32_t pin) {
  return pin >= 0 && pin <= configuredHighest && GPIO_IS_VALID_GPIO(pin);
}

String description(uint8_t pin) {
  String result = "gpio=" + String(pin);
  if (!GPIO_IS_VALID_GPIO(pin)) return result + " invalid";
  result += reservations[pin] ? " reserved=" + String(reservations[pin])
                              : " candidate=free";
  result += GPIO_IS_VALID_OUTPUT_GPIO(pin) ? " output=1" : " output=0";
  result += " level=" + String(gpio_get_level(static_cast<gpio_num_t>(pin)));
  result += " pull_test=" + String(pullAllowed[pin] ? 1 : 0);
  return result;
}
}

namespace Esp32GpioInspector {
bool begin(uint8_t highestPin) {
  configuredHighest = highestPin > MAX_GPIO ? MAX_GPIO : highestPin;
  return true;
}

bool reserve(uint8_t pin, const char *reason) {
  if (pin > MAX_GPIO || !reason) return false;
  reservations[pin] = reason;
  pullAllowed[pin] = false;
  return true;
}

bool allowPullTest(uint8_t pin) {
  if (pin > configuredHighest || reservations[pin] ||
      !GPIO_IS_VALID_GPIO(pin)) return false;
  pullAllowed[pin] = true;
  return true;
}

NativeResult inspect(const int32_t *arguments, uint8_t count) {
  if (count != 1 || !inRange(arguments[0]))
    return {false, 0, "usage: valid_gpio"};
  const uint8_t pin = arguments[0];
  return {true, gpio_get_level(static_cast<gpio_num_t>(pin)), description(pin)};
}

NativeResult audit(const int32_t *arguments, uint8_t count) {
  const int32_t page = count ? arguments[0] : 0;
  if (page < 0 || page > configuredHighest / 8)
    return {false, 0, "page out of range"};
  const int first = page * 8;
  String detail = "page=" + String(page);
  int32_t candidates = 0;
  for (int pin = first; pin <= configuredHighest && pin < first + 8; ++pin) {
    detail += " [" + String(pin) + "]=";
    if (!GPIO_IS_VALID_GPIO(pin)) detail += "invalid";
    else if (reservations[pin]) detail += String("reserved:") + reservations[pin];
    else { detail += "candidate"; ++candidates; }
  }
  return {true, candidates, detail};
}

NativeResult pullTest(const int32_t *arguments, uint8_t count) {
  if (count != 1 || !inRange(arguments[0]))
    return {false, 0, "usage: valid_gpio"};
  const uint8_t pin = arguments[0];
  if (!pullAllowed[pin])
    return {false, 0, "pin not in board active-test allowlist"};
  pinMode(pin, INPUT_PULLUP);
  delay(2);
  const int high = digitalRead(pin);
  pinMode(pin, INPUT_PULLDOWN);
  delay(2);
  const int low = digitalRead(pin);
  pinMode(pin, INPUT);
  const int follows = high == HIGH && low == LOW;
  return {true, follows, "gpio=" + String(pin) + " pullup=" + String(high) +
                              " pulldown=" + String(low) +
                              " restored=input"};
}
}
