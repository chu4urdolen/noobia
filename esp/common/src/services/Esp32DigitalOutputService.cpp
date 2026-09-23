#include "services/Esp32DigitalOutputService.h"

namespace Esp32DigitalOutputService {
NativeResult set(int pin, bool high) {
  pinMode(pin, OUTPUT);
  digitalWrite(pin, high ? HIGH : LOW);
  const int actual = digitalRead(pin);
  const String detail = "pin=" + String(pin) +
      " requested=" + String(high ? 1 : 0) +
      " actual=" + String(actual);
  return actual == (high ? HIGH : LOW)
      ? NativeResult{true, actual, detail}
      : NativeResult{false, actual, detail + " output_mismatch=1"};
}
}

NativeResult Esp32DigitalOutputFunction::call(const int32_t *arguments,
                                              uint8_t count) {
  if (count != 1 || arguments[0] < 0 || arguments[0] > 1)
    return {false, 0, "usage: state(0|1)"};
  return Esp32DigitalOutputService::set(pin_, arguments[0] != 0);
}
