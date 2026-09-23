#pragma once

#include "syscalls/NativeRegistry.h"

namespace MonotonicTimeService {
uint32_t milliseconds();
NativeResult now(const int32_t *arguments, uint8_t count);
NativeResult reset(const int32_t *arguments, uint8_t count);
}
