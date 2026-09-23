#pragma once

#include "syscalls/NativeRegistry.h"

// Reusable carrier transmitter and active-low receiver service.
namespace Esp32IrService {
struct Config {
  int txPin;
  int rxPin;
  uint32_t defaultFrequencyHz;
  uint32_t sampleIntervalUs;
  uint32_t loopbackBurstUs;
  uint32_t loopbackPauseMs;
  uint8_t pwmResolutionBits;
  uint32_t pwmDuty;
};

bool begin(const Config &config);
NativeResult send(const int32_t *arguments, uint8_t count);
NativeResult read(const int32_t *arguments, uint8_t count);
NativeResult loopback(const int32_t *arguments, uint8_t count);
}
