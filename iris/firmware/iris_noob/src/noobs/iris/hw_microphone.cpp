#include "iris.h"
#include "iris_config.h"

#include <services/Esp32I2sMicService.h>

bool irisMicrophoneBegin() {
  return Esp32I2sMicService::begin(IrisPins::MIC_BCLK, IrisPins::MIC_WS,
                                   IrisPins::MIC_DATA);
}
