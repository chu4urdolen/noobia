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
