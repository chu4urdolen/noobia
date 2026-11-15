#pragma once

#include "syscalls/NativeRegistry.h"

// Generic, board-aware GPIO diagnostics. The common service knows ESP32 GPIO
// validity; each physical Noob supplies reservations and active-test consent.
namespace Esp32GpioInspector {
bool begin(uint8_t highestPin);
bool reserve(uint8_t pin, const char *reason);
bool allowPullTest(uint8_t pin);
NativeResult inspect(const int32_t *arguments, uint8_t count);
NativeResult audit(const int32_t *arguments, uint8_t count);
NativeResult pullTest(const int32_t *arguments, uint8_t count);
}
