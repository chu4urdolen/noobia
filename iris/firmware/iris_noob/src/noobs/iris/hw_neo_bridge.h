#pragma once

#include <syscalls/noob_native_registry.h>
#include <core/noob_background_service.h>
#include <vm/noob_vm.h>

namespace IrisNeoBridge {
NativeResult caps(const int32_t *arguments, uint8_t count);
NativeResult irStatus(const int32_t *arguments, uint8_t count);
NativeResult irScanStart(const int32_t *arguments, uint8_t count);
NativeResult irScanStop(const int32_t *arguments, uint8_t count);
NativeResult irScanRead(const int32_t *arguments, uint8_t count);
NativeResult fileDownload(const int32_t *, uint8_t count, const String &path);
NativeResult audioPlay(const int32_t *, uint8_t count, const String &name);
NativeResult fileStatus(const int32_t *, uint8_t count);
NativeResult vmDownload(const int32_t *, uint8_t count, const String &name);
NativeResult imageFormat(const int32_t *, uint8_t, const String &name);
NativeResult oledDraw(const int32_t *, uint8_t, const String &name);
NativeResult oledText(const int32_t *, uint8_t, const String &text);
NativeResult displayStart(const int32_t *, uint8_t, const String &name);
NativeResult displayStop(const int32_t *, uint8_t);
NativeResult displayStatus(const int32_t *, uint8_t);
NoobBackgroundService &displayService(NoobVm &vm);
}
