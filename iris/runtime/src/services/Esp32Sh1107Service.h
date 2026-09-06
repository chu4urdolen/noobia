#pragma once

#include "syscalls/NativeRegistry.h"

namespace Esp32Sh1107Service {
bool begin(int sdaPin, int sclPin, uint8_t address = 0x3c);
NativeResult testPattern(const int32_t *arguments, uint8_t count);
}
