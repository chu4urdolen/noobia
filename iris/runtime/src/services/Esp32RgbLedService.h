#pragma once

#include <Arduino.h>
#include "syscalls/NativeRegistry.h"

// Reusable service for a single-wire WS2812/SK6812-style RGB status LED.
namespace Esp32RgbLedService {
bool begin(uint8_t pin);
NativeResult set(const int32_t *arguments, uint8_t argumentCount);
}
