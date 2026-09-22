#pragma once

#include "syscalls/NativeRegistry.h"

namespace MonotonicTimeService {
NativeResult now(const int32_t *arguments, uint8_t count);
}
