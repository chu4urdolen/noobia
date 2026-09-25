#pragma once
#include "syscalls/noob_native_registry.h"
namespace Esp32AdcService {
// Board-selected channels only; ADC unit handles persist for safe polling.
bool configure(uint8_t channel, int pin);
NativeResult read(const int32_t *args, uint8_t count);
}
