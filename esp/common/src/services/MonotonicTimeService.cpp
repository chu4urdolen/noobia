#include "services/MonotonicTimeService.h"

#include <Arduino.h>

namespace {
uint32_t epochMilliseconds = 0;
}

namespace MonotonicTimeService {
uint32_t milliseconds() { return millis() - epochMilliseconds; }

NativeResult now(const int32_t *, uint8_t count) {
  if (count) return {false, 0, "usage: no arguments"};
  const uint32_t value = milliseconds();
  return {true, static_cast<int32_t>(value),
          "monotonic_ms=" + String(value) + " wrap_bits=32"};
}

NativeResult reset(const int32_t *, uint8_t count) {
  if (count) return {false, 0, "usage: no arguments"};
  epochMilliseconds = millis();
  return {true, 0, "monotonic_ms=0"};
}
}
