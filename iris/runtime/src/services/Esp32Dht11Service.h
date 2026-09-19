#pragma once
#include "syscalls/NativeRegistry.h"
namespace Esp32Dht11Service {
bool begin(int pin);
NativeResult read(const int32_t *args, uint8_t count);
}
