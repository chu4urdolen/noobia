#include "iris.h"
#include "iris_config.h"
#include "hw_artifacts.h"

#include <services/Esp32SdMmcService.h>

bool irisStorageBegin() {
  const Esp32SdMmcService::Config config = {
      IrisPins::SD_CLK, IrisPins::SD_CMD, IrisPins::SD_D0, IrisPins::SD_D3,
      IrisHardware::SD_MOUNT, IrisHardware::CAPTURE_DIRECTORY,
      IrisHardware::CAPTURE_PREFIX, IrisHardware::SD_CLOCK_KHZ};
  return Esp32SdMmcService::begin(config) && irisArtifactsBegin();
}
