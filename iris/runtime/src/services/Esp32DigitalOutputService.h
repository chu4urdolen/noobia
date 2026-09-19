#pragma once

#include <Arduino.h>
#include "syscalls/NativeRegistry.h"

// Reusable one-pin output primitive. Board modules decide which pins callers
// may reach; this service contains no board names or pin map.
namespace Esp32DigitalOutputService {
NativeResult set(int pin, bool high);
}
