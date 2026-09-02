#include "services/Esp32CameraService.h"

#include <Preferences.h>
#include <SD_MMC.h>
#include "services/Esp32SdMmcService.h"

namespace {
bool cameraReady = false;
Preferences captureState;
}

namespace Esp32CameraService {
bool begin(const camera_config_t &config, const char *preferenceNamespace) {
  cameraReady = esp_camera_init(&config) == ESP_OK;
  captureState.begin(preferenceNamespace, false);
  return cameraReady;
}

NativeResult capture(const int32_t *, uint8_t) {
  if (!cameraReady) return {false, 0, "camera unavailable"};
  if (!Esp32SdMmcService::ready()) return {false, 0, "SD unavailable"};
  camera_fb_t *frame = esp_camera_fb_get();
  if (!frame) return {false, 0, "frame acquisition failed"};

  uint32_t sequence = captureState.getUInt("sequence", 0);
  String path;
  do {
    path = Esp32SdMmcService::capturePath(++sequence);
  } while (SD_MMC.exists(path));

  File output = SD_MMC.open(path, FILE_WRITE);
  const size_t expected = frame->len;
  const size_t written = output ? output.write(frame->buf, frame->len) : 0;
  if (output) output.close();
  esp_camera_fb_return(frame);
  if (written != expected) {
    SD_MMC.remove(path);
    return {false, 0, "SD write failed"};
  }
  captureState.putUInt("sequence", sequence);
  return {true, static_cast<int32_t>(sequence), path};
}
}
