#include "services/Esp32I2sMicService.h"

#include <ESP_I2S.h>
#include <math.h>

namespace {
I2SClass microphone;
bool microphoneReady = false;

NativeResult measureLevel() {
  if (!microphoneReady) return {false, 0, "microphone unavailable"};
  int32_t words[256];
  const size_t bytes = microphone.readBytes(
      reinterpret_cast<char *>(words), sizeof(words));
  const size_t count = bytes / sizeof(words[0]);
  if (!count) return {false, 0, "no microphone samples"};

  double sum = 0;
  double squares = 0;
  for (size_t index = 0; index < count; ++index) {
    // The microphone supplies signed audio left-aligned in a 32-bit word.
    // Converting to 16-bit scale gives VM programs practical thresholds.
    const int32_t sample = words[index] >> 16;
    sum += sample;
    squares += double(sample) * sample;
  }
  const double mean = sum / count;
  const int32_t rms = static_cast<int32_t>(
      sqrt(max(0.0, squares / count - mean * mean)));
  return {true, rms, "rms=" + String(rms)};
}
}

namespace Esp32I2sMicService {
bool begin(int bclkPin, int wsPin, int dataPin, uint32_t sampleRate) {
  microphone.setPins(bclkPin, wsPin, -1, dataPin);
  microphoneReady = microphone.begin(I2S_MODE_STD, sampleRate,
                                     I2S_DATA_BIT_WIDTH_32BIT,
                                     I2S_SLOT_MODE_MONO);
  if (!microphoneReady) return false;

  // Discard startup settling data so the first VM measurement is meaningful.
  int32_t discard[256];
  for (uint8_t pass = 0; pass < 4; ++pass) {
    microphone.readBytes(reinterpret_cast<char *>(discard), sizeof(discard));
  }
  return true;
}

bool ready() { return microphoneReady; }

NativeResult level(const int32_t *, uint8_t) { return measureLevel(); }

NativeResult above(const int32_t *arguments, uint8_t argumentCount) {
  if (argumentCount != 1 || arguments[0] < 0) {
    return {false, 0, "MIC_ABOVE expects nonnegative threshold"};
  }
  NativeResult result = measureLevel();
  if (!result.ok) return result;
  const int32_t rms = result.value;
  result.value = rms >= arguments[0] ? 1 : 0;
  result.detail += " threshold=" + String(arguments[0]);
  return result;
}
}
