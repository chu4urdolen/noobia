#include "core/NoobThreadProgram.h"

NoobThreadProgram::NoobThreadProgram(uint32_t intervalMs)
    : NoobProgram(NoobProgramType::THREAD), intervalMs_(intervalMs) {}

NativeResult NoobThreadProgram::call(const int32_t *arguments, uint8_t count) {
  if (count > 1 || (count && arguments[0] < 1))
    return {false, 0, "usage: [interval_ms]"};
  if (count) intervalMs_ = arguments[0];
  results_.clear();
  onStart();
  running_ = true;
  nextAt_ = millis();
  return {true, 1, "type=thread running=1 interval_ms=" + String(intervalMs_)};
}

NativeResult NoobThreadProgram::stop() {
  running_ = false;
  onStop();
  return {true, 0, "type=thread running=0 queued=" + String(results_.size())};
}

NativeResult NoobThreadProgram::status() const {
  return {true, running_ ? 1 : 0,
          "type=thread running=" + String(running_ ? 1 : 0) +
              " interval_ms=" + String(intervalMs_) +
              " channel_busy=" + String(channelBusy_[0] ? 1 : 0) +
              " queued=" + String(results_.size()) +
              " dropped=" + String(results_.dropped())};
}

NativeResult NoobThreadProgram::pop() {
  int32_t value = 0;
  if (!results_.pop(value)) return {false, 0, "thread queue empty"};
  return {true, value, "remaining=" + String(results_.size()) +
                           " dropped=" + String(results_.dropped())};
}

NativeResult NoobThreadProgram::poll() {
  int32_t value = 0;
  if (!results_.pop(value)) return {true, 0, "event=0 queued=0"};
  return {true, value, "event=1 remaining=" + String(results_.size()) +
                           " dropped=" + String(results_.dropped())};
}

bool NoobThreadProgram::tick(String &event) {
  if (!running_ || static_cast<int32_t>(millis() - nextAt_) < 0)
    return false;
  nextAt_ = millis() + intervalMs_;
  channelBusy_[0] = true;
  const bool emitted = step(event);
  channelBusy_[0] = false;
  return emitted;
}
