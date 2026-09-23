#include "iris_threads.h"

#include "iris_config.h"
#include <services/MonotonicTimeService.h>

namespace {
class IrisUltrasonicChangeThread final : public NoobThreadProgram {
 public:
  IrisUltrasonicChangeThread()
      : NoobThreadProgram(IrisHardware::ULTRASONIC_CHANGE_INTERVAL_MS) {}

  void begin(NativeRegistry &registry) {
    registry_ = &registry;
    distance_.configure(IrisFunctions::DISTANCE_MM, nullptr, 0);
  }

  NativeResult call(const int32_t *arguments, uint8_t count) override {
    if (count > 2 || (count && arguments[0] < 1) ||
        (count > 1 && arguments[1] < 50))
      return {false, 0, "usage: [change_mm] [interval_ms>=50]"};
    if (count) thresholdMm_ = arguments[0];
    if (count > 1) setInterval(arguments[1]);
    NativeResult result = NoobThreadProgram::call(nullptr, 0);
    result.detail += " change_mm=" + String(thresholdMm_);
    return result;
  }

 protected:
  void onStart() override {
    havePrevious_ = false;
    armed_ = true;
    stableSamples_ = 0;
    distance_.configure(IrisFunctions::DISTANCE_MM, nullptr, 0);
  }

  bool step(String &event) override {
    if (!registry_) return false;
    distance_.invoke(*registry_, 0);
    if (!distance_.lastOk()) {
      event = "NRP/1 0 EVENT ULTRASONIC_CHANGE_ERROR detail=" +
              distance_.lastDetail();
      return true;
    }
    int32_t current = 0;
    if (!distance_.results().pop(current)) return false;
    if (!havePrevious_) {
      previousMm_ = current;
      havePrevious_ = true;
      return false;
    }
    const int32_t delta =
        current > previousMm_ ? current - previousMm_ : previousMm_ - current;
    previousMm_ = current;
    if (!armed_) {
      const int32_t rearmMargin = thresholdMm_ / 4 > 5
                                      ? thresholdMm_ / 4
                                      : 5;
      stableSamples_ = delta <= rearmMargin ? stableSamples_ + 1 : 0;
      if (stableSamples_ >= IrisHardware::ULTRASONIC_CHANGE_REARM_SAMPLES) {
        armed_ = true;
        stableSamples_ = 0;
      }
      return false;
    }
    if (delta < thresholdMm_) return false;
    const uint32_t detectedAt = MonotonicTimeService::milliseconds();
    publish(static_cast<int32_t>(detectedAt));
    armed_ = false;
    stableSamples_ = 0;
    event = "NRP/1 0 EVENT ULTRASONIC_CHANGE time_ms=" + String(detectedAt);
    return true;
  }

 private:
  NativeRegistry *registry_ = nullptr;
  NoobProgramChannel distance_;
  int32_t thresholdMm_ = IrisHardware::ULTRASONIC_CHANGE_THRESHOLD_MM;
  int32_t previousMm_ = 0;
  bool havePrevious_ = false;
  bool armed_ = true;
  uint8_t stableSamples_ = 0;
};

IrisUltrasonicChangeThread ultrasonicChange;
NoobThreadStopFunction ultrasonicChangeStop(ultrasonicChange);
NoobThreadStatusFunction ultrasonicChangeStatus(ultrasonicChange);
NoobThreadPopFunction ultrasonicChangePop(ultrasonicChange);
NoobThreadPollFunction ultrasonicChangePoll(ultrasonicChange);
}

void irisThreadsBegin(NativeRegistry &registry) {
  ultrasonicChange.begin(registry);
}

NoobThreadProgram &irisUltrasonicChangeThread() {
  return ultrasonicChange;
}
NoobFunction &irisUltrasonicChangeStop() { return ultrasonicChangeStop; }
NoobFunction &irisUltrasonicChangeStatus() { return ultrasonicChangeStatus; }
NoobFunction &irisUltrasonicChangePop() { return ultrasonicChangePop; }
NoobFunction &irisUltrasonicChangePoll() { return ultrasonicChangePoll; }
