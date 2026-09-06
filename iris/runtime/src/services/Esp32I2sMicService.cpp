#include "services/Esp32I2sMicService.h"

#include <ESP_I2S.h>
#include <math.h>
#include "services/Esp32SdMmcService.h"

namespace {
I2SClass microphone;
bool microphoneReady = false;
uint32_t microphoneSampleRate = 16000;

void put16(uint8_t *out, uint16_t value) {
  out[0] = value & 255;
  out[1] = value >> 8;
}

void put32(uint8_t *out, uint32_t value) {
  for (uint8_t index = 0; index < 4; ++index) out[index] = value >> (index * 8);
}

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
  microphoneSampleRate = sampleRate;

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

NativeResult recordWav(const int32_t *arguments, uint8_t argumentCount) {
  if (!microphoneReady) return {false, 0, "microphone unavailable"};
  if (!Esp32SdMmcService::ready()) return {false, 0, "SD unavailable"};
  const int32_t seconds = argumentCount ? arguments[0] : 1;
  if (seconds < 1 || seconds > 30) return {false, 0, "duration must be 1..30 seconds"};
  fs::FS &storage = Esp32SdMmcService::fs();
  storage.mkdir("/audio");
  const String path = "/audio/audio_" + String(millis()) + ".wav";
  File file = storage.open(path, FILE_WRITE);
  if (!file) return {false, 0, "cannot create WAV"};
  uint8_t header[44] = {};
  memcpy(header, "RIFF", 4);
  memcpy(header + 8, "WAVEfmt ", 8);
  put32(header + 16, 16);
  put16(header + 20, 1);
  put16(header + 22, 1);
  put32(header + 24, microphoneSampleRate);
  put32(header + 28, microphoneSampleRate * 2);
  put16(header + 32, 2);
  put16(header + 34, 16);
  memcpy(header + 36, "data", 4);
  file.write(header, sizeof(header));

  const uint32_t wanted = microphoneSampleRate * uint32_t(seconds);
  uint32_t writtenSamples = 0;
  int32_t words[256];
  int16_t samples[256];
  while (writtenSamples < wanted) {
    const size_t bytes = microphone.readBytes(reinterpret_cast<char *>(words), sizeof(words));
    size_t count = bytes / sizeof(words[0]);
    if (count > wanted - writtenSamples) count = wanted - writtenSamples;
    if (!count) break;
    for (size_t index = 0; index < count; ++index) samples[index] = words[index] >> 16;
    if (file.write(reinterpret_cast<uint8_t *>(samples), count * 2) != count * 2) break;
    writtenSamples += count;
  }
  const uint32_t dataBytes = writtenSamples * 2;
  put32(header + 4, 36 + dataBytes);
  put32(header + 40, dataBytes);
  file.seek(0);
  file.write(header, sizeof(header));
  file.close();
  if (writtenSamples != wanted) return {false, int32_t(writtenSamples), "incomplete WAV=" + path};
  return {true, int32_t(writtenSamples), "path=" + path + " seconds=" + String(seconds)};
}
}
