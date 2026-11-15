#include "noob_self_test.h"
#include <cstring>

bool NoobSelfTest::record(const char *name, State state) {
  if (!name || !*name || strlen(name) >= sizeof(Check::name) || uint8_t(state) > 4) return false;
  for (uint8_t i = 0; i < count_; ++i) {
    if (!strcmp(checks_[i].name, name)) {
      checks_[i].state = state;
      return true;
    }
  }
  if (count_ == MAX_CHECKS) return false;
  strncpy(checks_[count_].name, name, sizeof(Check::name) - 1);
  checks_[count_++].state = state;
  return true;
}

bool NoobSelfTest::addProbe(const char *name, uint16_t id,
                           const int32_t *arguments, uint8_t count,
                           uint8_t attempts, uint32_t retryMs,
                           bool pendingOnFailure, const char *ascii) {
  if (!registry_ || probeCount_ == MAX_PROBES || count > 4 ||
      (count && !arguments) || !attempts || attempts > 3 || retryMs > 60000 ||
      !ascii || strlen(ascii) > 128 || !record(name, State::PENDING)) return false;
  Probe &probe = probes_[probeCount_++];
  strncpy(probe.name, name, sizeof(probe.name) - 1);
  probe.id = id;
  probe.count = count;
  probe.attempts = attempts;
  probe.retryMs = retryMs;
  probe.pendingOnFailure = pendingOnFailure;
  probe.ascii = ascii;
  for (uint8_t i = 0; i < count; ++i) probe.arguments[i] = arguments[i];
  return true;
}

NativeResult NoobSelfTest::call(const int32_t *, uint8_t count) {
  if (count) return {false, 0, "usage: no arguments"};
  const char *names[] = {"untested", "ready", "failed", "pending", "disabled"};
  int32_t totals[5] = {};
  String detail = "scope=boot_init complete=" + String(finished_ ? 1 : 0) + " checks=";
  for (uint8_t i = 0; i < count_; ++i) {
    const uint8_t state = uint8_t(checks_[i].state);
    ++totals[state];
    if (i) detail += ',';
    detail += String(checks_[i].name) + ":" + names[state];
  }
  NoobRecord result;
  result.add("value", totals[2]);
  result.add("ready", totals[1]);
  result.add("pending", totals[3]);
  result.add("untested", totals[0]);
  result.add("disabled", totals[4]);
  result.add("boot_ms", int32_t(millis()));
  return {true, totals[2], detail, result};
}

bool NoobSelfTest::tick(String &event) {
  if (planReady_ && !finished_ && int32_t(millis() - nextAt_) >= 0) {
    if (nextProbe_ == probeCount_) {
      finished_ = true;
      eventPending_ = true;
    } else {
      Probe &probe = probes_[nextProbe_];
      const NativeEntry *entry = registry_->find(probe.id);
      NativeResult result = entry ? registry_->callMixed(*entry, probe.arguments, probe.count, probe.ascii)
                                  : NativeResult{false, 0, "function disabled"};
      ++probe.tried;
      bool retry = !result.ok && entry && probe.tried < probe.attempts;
      State state = result.ok ? State::READY : !entry ? State::NOT_AVAILABLE :
          retry || probe.pendingOnFailure ? State::PENDING : State::FAILED;
      record(probe.name, state);
      nextAt_ = millis() + (retry ? probe.retryMs : 0);
      if (!retry) ++nextProbe_;
      event = "NRP/1 0 EVENT SELF_TEST_PROBE name=" + String(probe.name) +
          " ok=" + String(result.ok ? 1 : 0) + " attempt=" + String(probe.tried) +
          " retry=" + String(retry ? 1 : 0) + " detail=" + result.detail;
      return true;
    }
  }
  if (!eventPending_) return false;
  eventPending_ = false;
  const NativeResult report = call(nullptr, 0);
  event = "NRP/1 0 EVENT SELF_TEST failures=" + String(report.value) + " " + report.detail;
  return true;
}
