#pragma once

#include <esp_camera.h>
#include "syscalls/NativeRegistry.h"

namespace Esp32CameraService {
bool begin(const camera_config_t &config, const char *preferenceNamespace);
NativeResult capture(const int32_t *arguments, uint8_t count);
NativeResult recordMjpeg(const int32_t *arguments, uint8_t count);
}
