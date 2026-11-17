#include "servo_functions.h"

#include <Servo.h>
#include <services/SequenceService.h>
#include "lolth_config.h"

namespace {
constexpr int MIN_ANGLE = 10;
constexpr int MAX_ANGLE = 170;
constexpr int MIN_PULSE_US = 400;
constexpr int MAX_PULSE_US = 2400;
constexpr int DEFAULT_STEP = 5;

Servo servos[8];
bool armed[8] = {};
uint8_t angle[8] = {90, 90, 90, 90, 90, 90, 90, 90};

bool validServo(int32_t id) { return id >= 1 && id <= 8; }

NativeResult state(uint8_t index) {
  NoobRecord record;
  record.add("angle", angle[index]);
  record.add("armed", armed[index] ? 1 : 0);
  record.add("gpio", LolthPins::SERVO[index]);
  record.add("factory_zero", LolthCalibration::FACTORY_ZERO[index]);
  return {true, angle[index],
          "servo=" + String(index + 1) + " armed=" + String(armed[index]),
          record};
}

class ServoStepFunction final : public NoobFunction {
 public:
  ServoStepFunction(uint8_t index, int8_t direction)
      : index_(index), direction_(direction) {}
  bool acceptsNumbers() const override { return true; }
  NativeResult call(const int32_t *arguments, uint8_t count) override {
    if (count > 2) return {false, 0, "usage: [degrees(1..20)] [enable(0|1)]"};
    const int32_t degrees = count ? arguments[0] : DEFAULT_STEP;
    const int32_t enable = count == 2 ? arguments[1] : 1;
    if (degrees < 1 || degrees > 20 || (enable != 0 && enable != 1))
      return {false, 0, "degrees 1..20; enable 0|1"};
    if (!enable) return state(index_);
    if (!armed[index_]) return {false, 0, "arm servo first"};
    const int next = int(angle[index_]) + direction_ * degrees;
    if (next < MIN_ANGLE || next > MAX_ANGLE)
      return {false, 0, "servo angle limit 10..170"};
    angle[index_] = static_cast<uint8_t>(next);
    servos[index_].write(next);
    return state(index_);
  }

 private:
  uint8_t index_;
  int8_t direction_;
};

ServoStepFunction steps[16] = {
    {0, +1}, {0, -1}, {1, +1}, {1, -1},
    {2, +1}, {2, -1}, {3, +1}, {3, -1},
    {4, +1}, {4, -1}, {5, +1}, {5, -1},
    {6, +1}, {6, -1}, {7, +1}, {7, -1}};
}

NoobFunction &lolthServoStepFunction(uint8_t index) { return steps[index]; }

NativeResult lolthServoArm(const int32_t *arguments, uint8_t count) {
  if (count != 2 || !validServo(arguments[0]) ||
      arguments[1] < MIN_ANGLE || arguments[1] > MAX_ANGLE)
    return {false, 0, "usage: servo(1..8) angle(10..170)"};
  const uint8_t index = arguments[0] - 1;
  angle[index] = arguments[1];
  if (!armed[index]) {
    // The ESP8266 Servo library takes an explicit first pulse. No neutral
    // pulse is emitted before the requested initial angle.
    const int pulse = map(angle[index], 0, 180, MIN_PULSE_US, MAX_PULSE_US);
    servos[index].attach(LolthPins::SERVO[index], MIN_PULSE_US,
                         MAX_PULSE_US, pulse);
    armed[index] = true;
  } else {
    servos[index].write(angle[index]);
  }
  return state(index);
}

NativeResult lolthServoSet(const int32_t *arguments, uint8_t count) {
  if (count != 2 || !validServo(arguments[0]) ||
      arguments[1] < MIN_ANGLE || arguments[1] > MAX_ANGLE)
    return {false, 0, "usage: servo(1..8) angle(10..170)"};
  const uint8_t index = arguments[0] - 1;
  if (!armed[index]) return {false, 0, "arm servo first"};
  angle[index] = arguments[1];
  servos[index].write(angle[index]);
  return state(index);
}

NativeResult lolthServoState(const int32_t *arguments, uint8_t count) {
  if (count != 1 || !validServo(arguments[0]))
    return {false, 0, "usage: servo(1..8)"};
  return state(arguments[0] - 1);
}

NativeResult lolthServoDetach(const int32_t *arguments, uint8_t count) {
  if (count != 1 || !validServo(arguments[0]))
    return {false, 0, "usage: servo(1..8)"};
  const uint8_t index = arguments[0] - 1;
  servos[index].detach();
  armed[index] = false;
  return state(index);
}

NativeResult lolthServoDetachAll(const int32_t *, uint8_t count) {
  if (count) return {false, 0, "usage: no arguments"};
  SequenceService::stop(nullptr, 0);
  for (uint8_t index = 0; index < 8; ++index) {
    servos[index].detach();
    armed[index] = false;
  }
  return {true, 8, "all servo pulses stopped"};
}
