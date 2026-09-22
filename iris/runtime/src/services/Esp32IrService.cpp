#include "services/Esp32IrService.h"

#include <Arduino.h>

namespace {
Esp32IrService::Config settings = {-1, -1, 0, 0, 0, 0, 0, 0};

void preparePins() {
  pinMode(settings.txPin, OUTPUT);
  digitalWrite(settings.txPin, LOW);
  pinMode(settings.rxPin, INPUT_PULLUP);
}

uint32_t sendCarrier(uint32_t frequency, uint32_t durationUs) {
  if (!ledcAttach(settings.txPin, frequency, settings.pwmResolutionBits)) return UINT32_MAX;
  ledcWrite(settings.txPin, settings.pwmDuty);
  const uint32_t deadline = micros() + durationUs;
  uint32_t receiverLow = 0;
  while (int32_t(micros() - deadline) < 0) {
    receiverLow += digitalRead(settings.rxPin) == LOW;
    delayMicroseconds(settings.sampleIntervalUs);
  }
  ledcWrite(settings.txPin, 0);
  ledcDetach(settings.txPin);
  pinMode(settings.txPin, OUTPUT);
  digitalWrite(settings.txPin, LOW);
  return receiverLow;
}
}

namespace Esp32IrService {
bool begin(const Config &config) {
  if (!GPIO_IS_VALID_OUTPUT_GPIO(config.txPin) ||
      !GPIO_IS_VALID_GPIO(config.rxPin) || config.txPin == config.rxPin ||
      !config.defaultFrequencyHz || !config.sampleIntervalUs ||
      !config.loopbackBurstUs || !config.pwmResolutionBits)
    return false;
  settings = config;
  preparePins();
  return true;
}

NativeResult send(const int32_t *arguments, uint8_t count) {
  if (settings.txPin < 0 || settings.rxPin < 0) return {false, 0, "IR unconfigured"};
  if (count > 2) return {false, 0, "usage: [duration_ms] [frequency_hz]"};
  const int32_t durationMs = count ? arguments[0] : 10;
  const int32_t frequency = count > 1 ? arguments[1] : settings.defaultFrequencyHz;
  if (durationMs < 1 || durationMs > 100 || frequency < 30000 || frequency > 60000)
    return {false, 0, "duration 1..100 ms; frequency 30000..60000 Hz"};
  preparePins();
  const uint32_t low = sendCarrier(uint32_t(frequency), uint32_t(durationMs) * 1000UL);
  if (low == UINT32_MAX) return {false, 0, "IR PWM attach failed"};
  return {true, int32_t(low), "tx=" + String(settings.txPin) + " rx=" + String(settings.rxPin) +
      " frequency=" + String(frequency) + " duration_ms=" + String(durationMs) +
      " rx_low_samples=" + String(low)};
}

NativeResult read(const int32_t *arguments, uint8_t count) {
  if (settings.txPin < 0 || settings.rxPin < 0) return {false, 0, "IR unconfigured"};
  if (count > 1) return {false, 0, "usage: [window_ms]"};
  const int32_t windowMs = count ? arguments[0] : 100;
  if (windowMs < 1 || windowMs > 2000)
    return {false, 0, "window must be 1..2000 ms"};
  preparePins();
  const uint32_t deadline = millis() + uint32_t(windowMs);
  uint32_t samples = 0;
  uint32_t low = 0;
  uint32_t edges = 0;
  int previous = digitalRead(settings.rxPin);
  while (int32_t(millis() - deadline) < 0) {
    const int level = digitalRead(settings.rxPin);
    low += level == LOW;
    edges += level != previous;
    previous = level;
    ++samples;
    delayMicroseconds(settings.sampleIntervalUs);
  }
  return {true, int32_t(edges), "pin=" + String(settings.rxPin) + " window_ms=" +
      String(windowMs) + " samples=" + String(samples) + " low=" +
      String(low) + " edges=" + String(edges) + " level=" + String(previous)};
}

NativeResult loopback(const int32_t *arguments, uint8_t count) {
  if (settings.txPin < 0 || settings.rxPin < 0) return {false, 0, "IR unconfigured"};
  if (count > 1) return {false, 0, "usage: [bursts]"};
  const int32_t bursts = count ? arguments[0] : 20;
  if (bursts < 1 || bursts > 100) return {false, 0, "bursts must be 1..100"};
  preparePins();
  uint32_t low = 0;
  uint32_t idleLow = 0;
  for (int32_t i = 0; i < bursts; ++i) {
    idleLow += digitalRead(settings.rxPin) == LOW;
    const uint32_t burstLow = sendCarrier(settings.defaultFrequencyHz,
                                           settings.loopbackBurstUs);
    if (burstLow == UINT32_MAX) return {false, 0, "IR PWM attach failed"};
    low += burstLow;
    delay(settings.loopbackPauseMs);
  }
  const bool stuckLow = idleLow == uint32_t(bursts);
  const bool detected = low > 0 && !stuckLow;
  return {true, detected ? 1 : 0, "tx=" + String(settings.txPin) + " rx=" +
      String(settings.rxPin) + " bursts=" + String(bursts) + " carrier_low=" +
      String(low) + " idle_low=" + String(idleLow) +
      " stuck_low=" + String(stuckLow ? 1 : 0) +
      " detected=" + String(detected ? 1 : 0)};
}
}
