#include "core/noob_change_thread.h"

#include "services/MonotonicTimeService.h"
#include "services/SequenceService.h"

NoobChangeThreadProgram::NoobChangeThreadProgram(
    uint16_t sourceFunctionId, const char *eventName, uint32_t intervalMs,
    int32_t changeThreshold, uint8_t rearmSamples,
    uint8_t pauseSequenceChannelMask)
    : NoobThreadProgram(intervalMs),
      sourceFunctionId_(sourceFunctionId),
      eventName_(eventName),
      changeThreshold_(changeThreshold),
      rearmSamples_(rearmSamples),
      pauseSequenceChannelMask_(pauseSequenceChannelMask) {}

void NoobChangeThreadProgram::begin(NativeRegistry &registry) {
  registry_ = &registry;
  source_.configure(sourceFunctionId_, nullptr, 0);
}

NativeResult NoobChangeThreadProgram::call(const int32_t *arguments,
                                           uint8_t count) {
  if (count > 2 || (count && arguments[0] < 1) ||
      (count > 1 && arguments[1] < 50))
    return {false, 0, "usage: [change_delta] [interval_ms>=50]"};
  if (count) changeThreshold_ = arguments[0];
  if (count > 1) setInterval(arguments[1]);
  NativeResult result = NoobThreadProgram::call(nullptr, 0);
  result.detail += " change_delta=" + String(changeThreshold_);
  return result;
}

void NoobChangeThreadProgram::onStart() {
  havePrevious_ = false;
  armed_ = true;
  stableSamples_ = 0;
  source_.configure(sourceFunctionId_, nullptr, 0);
}

bool NoobChangeThreadProgram::step(String &event) {
  if (!registry_) return false;
  // Stay running, but do not sample an input affected by an active sequence.
  // The first post-sequence sample becomes a fresh baseline.
  if (SequenceService::busyMask() & pauseSequenceChannelMask_) {
    havePrevious_ = false;
    return false;
  }
  source_.invoke(*registry_, 0, false);
  if (!source_.lastOk()) {
    event = "NRP/1 0 EVENT " + String(eventName_) +
            "_ERROR detail=" + source_.lastDetail();
    return true;
  }

  int32_t current = 0;
  if (!source_.results().pop(current)) return false;
  if (!havePrevious_) {
    previous_ = current;
    havePrevious_ = true;
    return false;
  }

  const int32_t delta =
      current > previous_ ? current - previous_ : previous_ - current;
  previous_ = current;
  if (!armed_) {
    const int32_t rearmMargin =
        changeThreshold_ / 4 > 5 ? changeThreshold_ / 4 : 5;
    stableSamples_ = delta <= rearmMargin ? stableSamples_ + 1 : 0;
    if (stableSamples_ >= rearmSamples_) {
      armed_ = true;
      stableSamples_ = 0;
    }
    return false;
  }
  if (delta < changeThreshold_) return false;

  const uint32_t detectedAt = MonotonicTimeService::milliseconds();
  publish(static_cast<int32_t>(detectedAt));
  armed_ = false;
  stableSamples_ = 0;
  event = "NRP/1 0 EVENT " + String(eventName_) +
          " time_ms=" + String(detectedAt);
  return true;
}
