#pragma once

#include <Arduino.h>
#include "syscalls/NativeRegistry.h"

// Reusable binary status-lamp service. A Noob supplies the documented pin.
namespace Esp32SignalLedService {
bool begin(uint8_t pin);
NativeResult set(const int32_t *arguments, uint8_t argumentCount);
}
