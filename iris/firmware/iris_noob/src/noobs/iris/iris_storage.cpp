#include "iris.h"
#include "iris_config.h"

#include <services/Esp32SdMmcService.h>

bool irisStorageBegin() {
  const Esp32SdMmcService::Config config = {
      IrisPins::SD_CLK, IrisPins::SD_CMD, IrisPins::SD_D0,
      "/sdcard", "/captured", "capture_"};
  return Esp32SdMmcService::begin(config);
}
