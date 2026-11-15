#include "core/noob_thread_program.h"

NoobThreadProgram::NoobThreadProgram(uint32_t intervalMs)
    : NoobProgram(NoobProgramType::THREAD), intervalMs_(intervalMs) {}

NativeResult NoobThreadProgram::call(const int32_t *arguments, uint8_t count) {
  if (count > 1 || (count && arguments[0] < 1))
    return {false, 0, "usage: [interval_ms]"};
  if (count) intervalMs_ = arguments[0];
  results_.clear();
  haveLastPopped_ = false;
  onStart();
  running_ = true;
  channelBusy_[0] = true;
  nextAt_ = millis();
  return {true, 1, "type=thread running=1 interval_ms=" + String(intervalMs_)};
}

NativeResult NoobThreadProgram::stop() {
  running_ = false;
  channelBusy_[0] = false;
  onStop();
  return {true, 0, "type=thread running=0 queued=" + String(results_.size())};
}

NativeResult NoobThreadProgram::status() const {
  String detail = "type=thread running=" + String(running_ ? 1 : 0) +
                  " interval_ms=" + String(intervalMs_) +
                  " channel_busy=" + String(channelBusy_[0] ? 1 : 0) +
                  " queued=" + String(results_.size()) +
                  " dropped=" + String(results_.dropped());
  detail += statusDetail();
  return {true, running_ ? 1 : 0, detail};
}

NativeResult NoobThreadProgram::pop() {
  NoobRecord record;
  if (!results_.pop(record)) return {false, 0, "thread queue empty"};
  lastPopped_ = record;
  haveLastPopped_ = true;
  int32_t value = 0;
  record.primary(value);
  return {true, value,
          "remaining=" + String(results_.size()) +
              " dropped=" + String(results_.dropped()),
          record};
}

NativeResult NoobThreadProgram::poll() {
  NoobRecord record;
  if (!results_.pop(record)) return {true, 0, "event=0 queued=0"};
  lastPopped_ = record;
  haveLastPopped_ = true;
  int32_t value = 0;
  record.primary(value);
  return {true, value,
          "event=1 remaining=" + String(results_.size()) +
              " dropped=" + String(results_.dropped()),
          record};
}

NativeResult NoobThreadProgram::field(const int32_t *arguments,
                                      uint8_t count) const {
  if (count != 1 || arguments[0] < 0 ||
      arguments[0] >= NoobRecord::MAX_FIELDS)
    return {false, 0, "usage: field_index(0..5)"};
  if (!haveLastPopped_) return {false, 0, "no popped thread record"};
  const char *name = nullptr;
  int32_t value = 0;
  if (!lastPopped_.get(uint8_t(arguments[0]), name, value))
    return {false, 0, "record field absent"};
  return {true, value,
          "field=" + String(arguments[0]) + " name=" + String(name)};
}

bool NoobThreadProgram::lastPopped(NoobRecord &record) const {
  if (!haveLastPopped_) return false;
  record = lastPopped_;
  return true;
}

bool NoobThreadProgram::tick(String &event) {
  if (!running_ || static_cast<int32_t>(millis() - nextAt_) < 0)
    return false;
  nextAt_ = millis() + intervalMs_;
  return step(event);
}
