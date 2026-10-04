#pragma once

#include <Arduino.h>
#include "syscalls/noob_native_registry.h"
#include "vm/noob_vm.h"
#include "core/noob_vm_lifecycle.h"

namespace Esp32VmProgramStore {
bool begin(NoobVm &vm, const char *directory = "/programs");
NoobVmLifecycle &lifecycle();
NativeResult restoreLast();
NativeResult lastStatus(const int32_t *arguments, uint8_t count);
NativeResult clearLast(const int32_t *arguments, uint8_t count);
NativeResult save(const String &arguments);
NativeResult load(const String &arguments);
NativeResult storeBytes(const String &name, const uint8_t *bytes,
                        size_t length, bool replace = false);
NativeResult list(const String &arguments);
NativeResult remove(const String &arguments);
}
