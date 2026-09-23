#pragma once

#include "syscalls/NativeRegistry.h"

namespace Esp32SoftI2cDiagnostics {
bool begin(int sdaPin, int sclPin);
bool probe(uint8_t address);
NativeResult scan(const int32_t *arguments, uint8_t count);
}
