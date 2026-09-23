#include "services/Esp32CameraService.h"

#include <Preferences.h>
#include <SD_MMC.h>
#include "services/Esp32SdMmcService.h"

namespace {
bool cameraReady = false;
esp_err_t cameraInitError = ESP_OK;
Preferences captureState;
}

namespace Esp32CameraService {
bool begin(const camera_config_t &config, const char *preferenceNamespace) {
  cameraInitError = esp_camera_init(&config);
  cameraReady = cameraInitError == ESP_OK;
  captureState.begin(preferenceNamespace, false);
  return cameraReady;
}

NativeResult capture(const int32_t *, uint8_t) {
  if (!cameraReady)
    return {false, int32_t(cameraInitError),
            "camera init=" + String(esp_err_to_name(cameraInitError))};
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

NativeResult recordMjpeg(const int32_t *arguments, uint8_t count) {
  if (!cameraReady)
    return {false, int32_t(cameraInitError),
            "camera init=" + String(esp_err_to_name(cameraInitError))};
  if (!Esp32SdMmcService::ready()) return {false, 0, "SD unavailable"};
  const int32_t seconds = count ? arguments[0] : 3;
  const int32_t fps = count > 1 ? arguments[1] : 5;
  if (seconds < 1 || seconds > 15 || fps < 1 || fps > 10)
    return {false, 0, "usage: seconds(1..15) fps(1..10)"};
  fs::FS &storage = Esp32SdMmcService::fs();
  storage.mkdir("/video");
  const String path = "/video/video_" + String(millis()) + ".mjpeg";
  File output = storage.open(path, FILE_WRITE);
  if (!output) return {false, 0, "cannot create MJPEG"};
  const uint32_t interval = 1000 / fps;
  const uint32_t wantedFrames = seconds * fps;
  uint32_t frames = 0;
  uint32_t nextFrame = millis();
  while (frames < wantedFrames) {
    const int32_t remaining = int32_t(nextFrame - millis());
    if (remaining > 0) delay(remaining);
    camera_fb_t *frame = esp_camera_fb_get();
    if (!frame) break;
    const size_t written = output.write(frame->buf, frame->len);
    const size_t expected = frame->len;
    esp_camera_fb_return(frame);
    if (written != expected) break;
    ++frames;
    nextFrame += interval;
  }
  output.close();
  if (frames != wantedFrames)
    return {false, int32_t(frames), "incomplete MJPEG=" + path};
  return {true, int32_t(frames), "path=" + path + " fps=" + String(fps)};
}
}
