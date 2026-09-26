#include "core/noob_sampling_thread.h"

NoobSamplingThreadProgram::NoobSamplingThreadProgram(
    uint16_t sourceFunctionId, const char *eventName, uint32_t intervalMs,
    uint32_t durationMs, const int32_t *sourceArguments,
    uint8_t sourceArgumentCount)
    : NoobThreadProgram(intervalMs),
      sourceFunctionId_(sourceFunctionId),
      eventName_(eventName),
      durationMs_(durationMs),
      sourceArgumentCount_(sourceArgumentCount) {
  if (!sourceArguments || sourceArgumentCount_ > MAX_SOURCE_ARGUMENTS)
    sourceArgumentCount_ = 0;
  for (uint8_t index = 0; index < sourceArgumentCount_; ++index)
    sourceArguments_[index] = sourceArguments[index];
}

void NoobSamplingThreadProgram::begin(NativeRegistry &registry) {
  registry_ = &registry;
  source_.configure(sourceFunctionId_, sourceArguments_, sourceArgumentCount_);
}

NativeResult NoobSamplingThreadProgram::call(const int32_t *arguments,
                                              uint8_t count) {
  if (count > 2 || (count && (arguments[0] < 0 || arguments[0] > 3600000)) ||
      (count > 1 && (arguments[1] < 50 || arguments[1] > 60000)))
    return {false, 0,
            "usage: [duration_ms(0..3600000)] [interval_ms(50..60000)]"};
  if (count) durationMs_ = arguments[0];
  if (count > 1) setInterval(arguments[1]);
  NativeResult result = NoobThreadProgram::call(nullptr, 0);
  result.detail += " duration_ms=" + String(durationMs_);
  return result;
}

void NoobSamplingThreadProgram::onStart() {
  startedAt_ = millis();
  source_.configure(sourceFunctionId_, sourceArguments_, sourceArgumentCount_);
}

bool NoobSamplingThreadProgram::step(String &event) {
  if (!registry_) return false;
  if (durationMs_ && uint32_t(millis() - startedAt_) >= durationMs_) {
    NoobThreadProgram::stop();
    event = "NRP/1 0 EVENT " + String(eventName_) + "_COMPLETE";
    return true;
  }
  source_.invoke(*registry_, 0, false);
  if (!source_.lastOk()) {
    event = "NRP/1 0 EVENT " + String(eventName_) +
            "_ERROR detail=" + source_.lastDetail();
    return true;
  }
  NoobRecord record;
  if (source_.results().pop(record)) publish(record);
  return false;
}

String NoobSamplingThreadProgram::statusDetail() const {
  const uint32_t elapsed = millis() - startedAt_;
  const uint32_t remaining =
      !durationMs_ || elapsed >= durationMs_ ? 0 : durationMs_ - elapsed;
  return " duration_ms=" + String(durationMs_) +
         " remaining_ms=" + String(remaining);
}
