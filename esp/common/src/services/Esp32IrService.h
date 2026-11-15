#pragma once

#include "syscalls/noob_native_registry.h"

// Reusable carrier transmitter and active-low receiver service.
namespace Esp32IrService {
constexpr size_t CAPTURE_MAX_PULSES = 8192;
struct Config {
  int txPin;
  int rxPin;
  uint32_t defaultFrequencyHz;
  uint32_t sampleIntervalUs;
  uint32_t loopbackBurstUs;
  uint32_t loopbackPauseMs;
  uint8_t pwmResolutionBits;
  uint32_t pwmDuty;
  uint32_t captureResolutionHz;
  uint32_t captureIdleUs;
  uint32_t captureMinPulseUs;
};

bool begin(const Config &config);
NativeResult send(const int32_t *arguments, uint8_t count);
NativeResult read(const int32_t *arguments, uint8_t count);
NativeResult loopback(const int32_t *arguments, uint8_t count);

// An edge interrupt timestamps the demodulated receiver signal in microseconds.
bool captureStart();
bool captureReady();
bool captureRearm();
void captureStop();
size_t capturePulseCount();
bool capturePulse(size_t index, uint8_t &level, uint32_t &durationUs);
size_t captureSymbolCount();
size_t captureSymbolCapacity();
uint32_t captureResolutionHz();
const String &captureError();
NativeResult replayEnvelope(const uint8_t *receiverLevels,
                            const uint32_t *durationsUs, size_t pulseCount,
                            uint8_t repeats = 1);
NativeResult replayAndCapture(const uint8_t *receiverLevels,
                              const uint32_t *durationsUs, size_t pulseCount,
                              uint8_t *capturedLevels,
                              uint32_t *capturedDurationsUs,
                              size_t capturedCapacity);
}
