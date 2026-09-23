#pragma once

#include <Arduino.h>
#include "syscalls/NativeRegistry.h"

// Reusable ESP32 I2S microphone service. Physical Noobs provide their pins;
// VM programs see only portable MIC_LEVEL and MIC_ABOVE native functions.
namespace Esp32I2sMicService {
bool begin(int bclkPin, int wsPin, int dataPin, uint32_t sampleRate = 16000);
bool ready();
NativeResult level(const int32_t *arguments, uint8_t argumentCount);
NativeResult above(const int32_t *arguments, uint8_t argumentCount);
NativeResult recordWav(const int32_t *arguments, uint8_t argumentCount);
}
