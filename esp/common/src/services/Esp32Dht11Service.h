#pragma once
#include "syscalls/noob_native_registry.h"
namespace Esp32Dht11Service {
bool begin(int pin);
NativeResult sample(int32_t &temperatureTenths, int32_t &humidityTenths);
NativeResult read(const int32_t *args, uint8_t count);
}
