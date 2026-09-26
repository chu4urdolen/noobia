#include "services/Esp32IrService.h"

#include <Arduino.h>
#include <esp32-hal-rmt.h>
#include <memory>
#include <new>

namespace {
Esp32IrService::Config settings = {-1, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0};
constexpr size_t CAPTURE_PULSE_CAPACITY = Esp32IrService::CAPTURE_MAX_PULSES;
volatile uint8_t captureLevels[CAPTURE_PULSE_CAPACITY] = {};
volatile uint32_t captureDurationsUs[CAPTURE_PULSE_CAPACITY] = {};
volatile size_t capturedPulses = 0;
volatile uint32_t captureLastEdgeUs = 0;
volatile uint8_t captureLastLevel = HIGH;
volatile bool captureOverflow = false;
volatile bool captureActive = false;
volatile bool captureFrameReady = false;
String lastCaptureError;

void preparePins() {
  pinMode(settings.txPin, OUTPUT);
  digitalWrite(settings.txPin, LOW);
  pinMode(settings.rxPin, INPUT_PULLUP);
}

void IRAM_ATTR captureEdge() {
  if (!captureActive || captureFrameReady) return;
  const uint32_t now = micros();
  const uint8_t level = digitalRead(settings.rxPin);
  const uint32_t duration = now - captureLastEdgeUs;
  // If the main loop is busy, the first edge after an idle gap closes the
  // previous frame. This prevents repeated remote-control frames merging.
  if (duration >= settings.captureIdleUs) {
    if (capturedPulses) captureFrameReady = true;
    captureLastEdgeUs = now;
    captureLastLevel = level;
    return;
  }
  if (duration >= settings.captureMinPulseUs &&
      !captureFrameReady) {
    const size_t index = capturedPulses;
    if (index < CAPTURE_PULSE_CAPACITY) {
      captureLevels[index] = captureLastLevel;
      captureDurationsUs[index] = duration;
      capturedPulses = index + 1;
    } else {
      captureOverflow = true;
    }
  }
  captureLastEdgeUs = now;
  captureLastLevel = level;
}

uint32_t sendCarrier(uint32_t frequency, uint32_t durationUs) {
  if (!ledcAttach(settings.txPin, frequency, settings.pwmResolutionBits)) return UINT32_MAX;
  ledcWrite(settings.txPin, settings.pwmDuty);
  const uint32_t deadline = micros() + durationUs;
  uint32_t receiverLow = 0;
  uint32_t samples = 0;
  while (int32_t(micros() - deadline) < 0) {
    receiverLow += digitalRead(settings.rxPin) == LOW;
    delayMicroseconds(settings.sampleIntervalUs);
    if (durationUs >= 100000 && ++samples % 32 == 0) delay(1);
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
      !config.loopbackBurstUs || !config.pwmResolutionBits ||
      config.captureResolutionHz < 100000 ||
      config.captureResolutionHz > 80000000 || !config.captureIdleUs ||
      config.captureMinPulseUs > config.captureIdleUs)
    return false;
  settings = config;
  preparePins();
  return true;
}

NativeResult send(const int32_t *arguments, uint8_t count) {
  if (settings.txPin < 0 || settings.rxPin < 0) return {false, 0, "IR unconfigured"};
  if (captureActive) return {false, 0, "IR capture active"};
  if (count > 3) return {false, 0, "usage: [duration_ms] [frequency_hz] [enabled]"};
  const int32_t durationMs = count ? arguments[0] : 10;
  const int32_t frequency = count > 1 ? arguments[1] : settings.defaultFrequencyHz;
  const int32_t enabled = count > 2 ? arguments[2] : 1;
  if (enabled < 0 || enabled > 1)
    return {false, 0, "enabled must be 0 or 1"};
  if (durationMs < 1 || durationMs > 10000 || frequency < 30000 || frequency > 60000)
    return {false, 0, "duration 1..10000 ms; frequency 30000..60000 Hz"};
  if (!enabled) return {true, 0, "skipped=1"};
  preparePins();
  const uint32_t low = sendCarrier(uint32_t(frequency), uint32_t(durationMs) * 1000UL);
  if (low == UINT32_MAX) return {false, 0, "IR PWM attach failed"};
  return {true, int32_t(low), "tx=" + String(settings.txPin) + " rx=" + String(settings.rxPin) +
      " frequency=" + String(frequency) + " duration_ms=" + String(durationMs) +
      " rx_low_samples=" + String(low)};
}

NativeResult read(const int32_t *arguments, uint8_t count) {
  if (settings.txPin < 0 || settings.rxPin < 0) return {false, 0, "IR unconfigured"};
  if (captureActive) return {false, 0, "IR capture active"};
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
  if (captureActive) return {false, 0, "IR capture active"};
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

bool captureStart() {
  if (settings.rxPin < 0 || captureActive) {
    lastCaptureError = captureActive ? "IR capture already active"
                                     : "IR unconfigured";
    return false;
  }
  pinMode(settings.rxPin, INPUT_PULLUP);
  capturedPulses = 0;
  captureOverflow = false;
  captureFrameReady = false;
  captureLastLevel = digitalRead(settings.rxPin);
  captureLastEdgeUs = micros();
  captureActive = true;
  lastCaptureError = "";
  attachInterrupt(settings.rxPin, captureEdge, CHANGE);
  return true;
}

bool captureReady() {
  if (!captureActive) return false;
  if (!captureFrameReady && capturedPulses &&
      uint32_t(micros() - captureLastEdgeUs) >= settings.captureIdleUs) {
    detachInterrupt(settings.rxPin);
    captureFrameReady = true;
  }
  return captureFrameReady;
}

bool captureRearm() {
  if (!captureActive) {
    lastCaptureError = "IR capture inactive";
    return false;
  }
  capturedPulses = 0;
  captureOverflow = false;
  captureFrameReady = false;
  captureLastLevel = digitalRead(settings.rxPin);
  captureLastEdgeUs = micros();
  attachInterrupt(settings.rxPin, captureEdge, CHANGE);
  return true;
}

void captureStop() {
  if (captureActive) detachInterrupt(settings.rxPin);
  captureActive = false;
  captureFrameReady = false;
  preparePins();
}

size_t capturePulseCount() {
  if (!captureReady()) return 0;
  return capturedPulses;
}

bool capturePulse(size_t index, uint8_t &level, uint32_t &durationUs) {
  if (!captureReady() || index >= capturedPulses) return false;
  level = captureLevels[index];
  durationUs = captureDurationsUs[index];
  return true;
}

size_t captureSymbolCount() { return (capturedPulses + 1) / 2; }
size_t captureSymbolCapacity() { return (CAPTURE_PULSE_CAPACITY + 1) / 2; }
uint32_t captureResolutionHz() { return settings.captureResolutionHz; }
const String &captureError() { return lastCaptureError; }

static NativeResult replayEnvelopeImpl(const uint8_t *receiverLevels,
                                       const uint32_t *durationsUs,
                                       size_t pulseCount, uint8_t repeats,
                                       bool allowCapture) {
  if (settings.txPin < 0 || settings.rxPin < 0)
    return {false, 0, "IR unconfigured"};
  if (captureActive && !allowCapture)
    return {false, 0, "IR capture active"};
  if (!receiverLevels || !durationsUs || !pulseCount ||
      pulseCount > CAPTURE_PULSE_CAPACITY || !repeats || repeats > 20)
    return {false, 0, "invalid IR envelope"};

  const size_t symbols = (pulseCount + 1) / 2;
  std::unique_ptr<rmt_data_t[]> output(
      new (std::nothrow) rmt_data_t[symbols]());
  if (!output) return {false, 0, "insufficient IR transmit memory"};
  uint64_t totalUs = 0;
  for (size_t index = 0; index < pulseCount; ++index) {
    if (!durationsUs[index] || durationsUs[index] > 32767)
      return {false, 0, "IR pulse duration outside 1..32767 us"};
    // Demodulating receiver modules are active-low: LOW means carrier present.
    const uint8_t carrierOn = receiverLevels[index] ? 0 : 1;
    rmt_data_t &symbol = output[index / 2];
    if (index & 1) {
      symbol.level1 = carrierOn;
      symbol.duration1 = durationsUs[index];
    } else {
      symbol.level0 = carrierOn;
      symbol.duration0 = durationsUs[index];
    }
    totalUs += durationsUs[index];
  }
  if (!rmtInit(settings.txPin, RMT_TX_MODE, RMT_MEM_NUM_BLOCKS_2,
               settings.captureResolutionHz))
    return {false, 0, "RMT transmit init failed"};
  const float duty = float(settings.pwmDuty) /
                     float(uint32_t(1) << settings.pwmResolutionBits);
  // The ESP-IDF flag is active-low; our RMT high level represents carrier on.
  if (!rmtSetCarrier(settings.txPin, true, false, settings.defaultFrequencyHz,
                     duty)) {
    rmtDeinit(settings.txPin);
    preparePins();
    return {false, 0, "RMT carrier setup failed"};
  }
  bool sent = true;
  for (uint8_t repeat = 0; repeat < repeats && sent; ++repeat)
    sent = rmtWrite(settings.txPin, output.get(), symbols, RMT_WAIT_FOR_EVER);
  rmtDeinit(settings.txPin);
  preparePins();
  if (!sent) return {false, 0, "RMT transmit failed"};
  return {true, int32_t(pulseCount),
          "pulses=" + String(pulseCount) + " repeats=" + String(repeats) +
              " carrier_hz=" + String(settings.defaultFrequencyHz) +
              " frame_us=" + String(uint32_t(totalUs))};
}

NativeResult replayEnvelope(const uint8_t *receiverLevels,
                            const uint32_t *durationsUs, size_t pulseCount,
                            uint8_t repeats) {
  return replayEnvelopeImpl(receiverLevels, durationsUs, pulseCount, repeats,
                            false);
}

NativeResult replayAndCapture(const uint8_t *receiverLevels,
                              const uint32_t *durationsUs, size_t pulseCount,
                              uint8_t *capturedLevels,
                              uint32_t *capturedDurationsUs,
                              size_t capturedCapacity) {
  if (captureActive) return {false, 0, "IR capture active"};
  if (!capturedLevels || !capturedDurationsUs || !capturedCapacity)
    return {false, 0, "invalid IR comparison buffer"};
  if (!captureStart()) return {false, 0, captureError()};
  delay((settings.captureIdleUs + 999) / 1000 + 2);
  NativeResult sent = replayEnvelopeImpl(receiverLevels, durationsUs,
                                         pulseCount, 1, true);
  if (!sent.ok) {
    captureStop();
    return sent;
  }
  delay((settings.captureIdleUs + 999) / 1000 + 2);
  const size_t observed = capturePulseCount();
  if (captureOverflow || observed > capturedCapacity) {
    captureStop();
    return {false, 0, "IR comparison capture overflow"};
  }
  for (size_t index = 0; index < observed; ++index) {
    if (!capturePulse(index, capturedLevels[index],
                      capturedDurationsUs[index])) {
      captureStop();
      return {false, 0, "IR comparison pulse copy failed"};
    }
  }
  captureStop();
  return {true, int32_t(observed),
          "sent_pulses=" + String(pulseCount) +
              " observed_pulses=" + String(observed) +
              " carrier_hz=" + String(settings.defaultFrequencyHz)};
}
}
