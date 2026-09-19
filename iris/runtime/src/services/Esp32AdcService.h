#pragma once
#include "syscalls/NativeRegistry.h"
namespace Esp32AdcService {
// Board-selected channels only; registration leaves hardware dormant.
bool configure(uint8_t channel, int pin);
NativeResult read(const int32_t *args, uint8_t count);
}
