#include "iris.h"
#include "iris_config.h"

#include <services/Esp32CameraService.h>

bool irisCameraBegin() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = IrisPins::CAMERA_D0;
  config.pin_d1 = IrisPins::CAMERA_D1;
  config.pin_d2 = IrisPins::CAMERA_D2;
  config.pin_d3 = IrisPins::CAMERA_D3;
  config.pin_d4 = IrisPins::CAMERA_D4;
  config.pin_d5 = IrisPins::CAMERA_D5;
  config.pin_d6 = IrisPins::CAMERA_D6;
  config.pin_d7 = IrisPins::CAMERA_D7;
  config.pin_xclk = IrisPins::CAMERA_XCLK;
  config.pin_pclk = IrisPins::CAMERA_PCLK;
  config.pin_vsync = IrisPins::CAMERA_VSYNC;
  config.pin_href = IrisPins::CAMERA_HREF;
  config.pin_sccb_sda = IrisPins::CAMERA_SDA;
  config.pin_sccb_scl = IrisPins::CAMERA_SCL;
  config.pin_pwdn = -1;
  config.pin_reset = -1;
  config.xclk_freq_hz = 10000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_SVGA;
  config.jpeg_quality = 12;
  config.fb_count = 2;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_LATEST;
  return Esp32CameraService::begin(config, "iris-capture");
}
