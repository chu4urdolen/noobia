#pragma once

#include <Arduino.h>
#include "syscalls/NativeRegistry.h"

namespace Esp32I2cService {
bool begin(int sdaPin, int sclPin, uint32_t frequency = 100000);
NativeResult scan(const int32_t *arguments, uint8_t count);
NativeResult write(const int32_t *arguments, uint8_t count);
NativeResult read(const int32_t *arguments, uint8_t count);
NativeResult writeRead(const int32_t *arguments, uint8_t count);
}
