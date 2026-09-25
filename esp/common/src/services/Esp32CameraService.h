#pragma once

#include <esp_camera.h>
#include "syscalls/noob_native_registry.h"

namespace Esp32CameraService {
bool begin(const camera_config_t &config, const char *preferenceNamespace);
NativeResult capture(const int32_t *arguments, uint8_t count);
NativeResult captureNamed(const char *prefix, uint32_t token);
NativeResult recordMjpeg(const int32_t *arguments, uint8_t count);
}
