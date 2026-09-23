#include "iris_threads.h"

#include "iris_config.h"

namespace {
class IrisUltrasonicChangeThread final : public NoobThreadProgram {
 public:
  IrisUltrasonicChangeThread() : NoobThreadProgram(250) {}

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
    haveBaseline_ = false;
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
    if (!haveBaseline_) {
      baselineMm_ = current;
      haveBaseline_ = true;
      return false;
    }
    const int32_t delta =
        current > baselineMm_ ? current - baselineMm_ : baselineMm_ - current;
    if (delta < thresholdMm_) return false;
    const int32_t previous = baselineMm_;
    baselineMm_ = current;
    publish(current);
    event = "NRP/1 0 EVENT ULTRASONIC_CHANGE distance_mm=" +
            String(current) + " previous_mm=" + String(previous) +
            " delta_mm=" + String(delta);
    return true;
  }

 private:
  NativeRegistry *registry_ = nullptr;
  NoobProgramChannel distance_;
  int32_t thresholdMm_ = 100;
  int32_t baselineMm_ = 0;
  bool haveBaseline_ = false;
};

IrisUltrasonicChangeThread ultrasonicChange;
NoobThreadStopFunction ultrasonicChangeStop(ultrasonicChange);
NoobThreadStatusFunction ultrasonicChangeStatus(ultrasonicChange);
NoobThreadPopFunction ultrasonicChangePop(ultrasonicChange);
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
