#pragma once

#include "syscalls/NativeRegistry.h"
#include "core/BackgroundService.h"

namespace Esp32WifiService {
bool begin();
NativeResult scan(const int32_t *arguments, uint8_t count);
NativeResult rssi(const int32_t *arguments, uint8_t count);
NativeResult rssiOn(const int32_t *arguments, uint8_t count);
NativeResult rssiOff(const int32_t *arguments, uint8_t count);
NoobBackgroundService &rssiService();
}
