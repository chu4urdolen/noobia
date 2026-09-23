#include "services/MonotonicTimeService.h"

#include <Arduino.h>

namespace {
uint32_t epochMilliseconds = 0;
}

namespace MonotonicTimeService {
NativeResult now(const int32_t *, uint8_t count) {
  if (count) return {false, 0, "usage: no arguments"};
  const uint32_t milliseconds = millis() - epochMilliseconds;
  return {true, static_cast<int32_t>(milliseconds),
          "monotonic_ms=" + String(milliseconds) + " wrap_bits=32"};
}

NativeResult reset(const int32_t *, uint8_t count) {
  if (count) return {false, 0, "usage: no arguments"};
  epochMilliseconds = millis();
  return {true, 0, "monotonic_ms=0"};
}
}
