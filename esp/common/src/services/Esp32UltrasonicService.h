#pragma once

#include "syscalls/noob_native_registry.h"

namespace Esp32UltrasonicService {
struct Config {
  int triggerPin;
  int echoPin;
  uint32_t triggerSettleUs;
  uint32_t triggerPulseUs;
  uint32_t interSampleMs;
  uint32_t soundSpeedMmPerSecond;
  uint8_t defaultSamples;
  uint32_t defaultTimeoutUs;
};

bool begin(const Config &config);
NativeResult measure(const int32_t *arguments, uint8_t count);
}
