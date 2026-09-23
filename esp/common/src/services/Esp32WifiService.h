#pragma once

#include "syscalls/NativeRegistry.h"
#include "core/BackgroundService.h"

namespace Esp32WifiService {
bool begin(const char *defaultSsid = nullptr, const char *defaultPassword = nullptr);
NativeResult scan(const int32_t *arguments, uint8_t count);
NativeResult rssi(const int32_t *arguments, uint8_t count);
NativeResult rssiOn(const int32_t *arguments, uint8_t count);
NativeResult rssiOff(const int32_t *arguments, uint8_t count);
NativeResult connect(const int32_t *arguments, uint8_t count);
NativeResult disconnect(const int32_t *arguments, uint8_t count);
NativeResult status(const int32_t *arguments, uint8_t count);
NativeResult setCredentials(const String &arguments);
NoobBackgroundService &rssiService();
}
