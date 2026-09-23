#pragma once

#include <Arduino.h>
#include "syscalls/NativeRegistry.h"
#include "vm/NoobVm.h"

namespace Esp32VmProgramStore {
bool begin(NoobVm &vm, const char *directory = "/programs");
NativeResult save(const String &arguments);
NativeResult load(const String &arguments);
NativeResult list(const String &arguments);
NativeResult remove(const String &arguments);
}
