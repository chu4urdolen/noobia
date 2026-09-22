#include "services/Esp32UltrasonicService.h"

#include <Arduino.h>

namespace {
Esp32UltrasonicService::Config settings = {-1, -1, 0, 0, 0, 0, 0, 0};
}

namespace Esp32UltrasonicService {
bool begin(const Config &config) {
  if (!GPIO_IS_VALID_OUTPUT_GPIO(config.triggerPin) ||
      !GPIO_IS_VALID_GPIO(config.echoPin) || config.triggerPin == config.echoPin ||
      !config.triggerPulseUs || !config.soundSpeedMmPerSecond ||
      !config.defaultSamples || !config.defaultTimeoutUs)
    return false;
  settings = config;
  pinMode(settings.triggerPin, OUTPUT);
  digitalWrite(settings.triggerPin, LOW);
  pinMode(settings.echoPin, INPUT);
  return true;
}

NativeResult measure(const int32_t *arguments, uint8_t count) {
  if (settings.triggerPin < 0 || settings.echoPin < 0)
    return {false, 0, "ultrasonic unconfigured"};
  if (count > 2) return {false, 0, "usage: [samples(1..10)] [timeout_us]"};
  const int32_t wanted = count ? arguments[0] : settings.defaultSamples;
  const int32_t timeoutUs = count > 1 ? arguments[1] : settings.defaultTimeoutUs;
  if (wanted < 1 || wanted > 10 || timeoutUs < 1000 || timeoutUs > 60000)
    return {false, 0, "samples 1..10; timeout 1000..60000 us"};

  uint32_t totalUs = 0;
  uint32_t minimumUs = UINT32_MAX;
  uint32_t maximumUs = 0;
  int received = 0;
  for (int32_t i = 0; i < wanted; ++i) {
    digitalWrite(settings.triggerPin, LOW);
    delayMicroseconds(settings.triggerSettleUs);
    digitalWrite(settings.triggerPin, HIGH);
    delayMicroseconds(settings.triggerPulseUs);
    digitalWrite(settings.triggerPin, LOW);
    const uint32_t durationUs = pulseIn(settings.echoPin, HIGH, uint32_t(timeoutUs));
    if (durationUs) {
      totalUs += durationUs;
      minimumUs = min(minimumUs, durationUs);
      maximumUs = max(maximumUs, durationUs);
      ++received;
    }
    delay(settings.interSampleMs);
  }
  if (!received)
    return {false, 0, "no echo trig=" + String(settings.triggerPin) +
        " echo=" + String(settings.echoPin) + " samples=" + String(wanted)};
  const uint32_t averageUs = totalUs / uint32_t(received);
  const uint64_t oneWayMicrometres =
      uint64_t(averageUs) * settings.soundSpeedMmPerSecond / 2;
  const int32_t distanceMm = int32_t((oneWayMicrometres + 500000) / 1000000);
  return {true, distanceMm, "distance_mm=" + String(distanceMm) +
      " echo_us=" + String(averageUs) + " min_us=" + String(minimumUs) +
      " max_us=" + String(maximumUs) + " received=" + String(received) +
      "/" + String(wanted) + " trig=" + String(settings.triggerPin) +
      " echo=" + String(settings.echoPin)};
}
}
