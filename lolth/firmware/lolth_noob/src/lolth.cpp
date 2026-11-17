#include "lolth.h"

#include "lolth_config.h"
#include "servo_functions.h"

NativeResult lolthDistanceMm(const int32_t *arguments, uint8_t count);
NoobFunction &lolthServo1Wiggle();

bool lolthRegister(NoobRuntime &runtime) {
  bool ok = true;
  runtime.capabilities().add("SERVO_8");
  runtime.capabilities().add("ULTRASONIC_MM");
  runtime.capabilities().add("WIFI_TCP");
  const char *names[] = {
      "SERVO1_UP", "SERVO1_DOWN", "SERVO2_UP", "SERVO2_DOWN",
      "SERVO3_UP", "SERVO3_DOWN", "SERVO4_UP", "SERVO4_DOWN",
      "SERVO5_UP", "SERVO5_DOWN", "SERVO6_UP", "SERVO6_DOWN",
      "SERVO7_UP", "SERVO7_DOWN", "SERVO8_UP", "SERVO8_DOWN"};
  for (uint8_t index = 0; index < 16; ++index)
    ok &= runtime.natives().add(LolthFunctions::SERVO1_UP + index,
                                names[index], lolthServoStepFunction(index));
  ok &= runtime.natives().add(LolthFunctions::SERVO_ARM, "SERVO_ARM",
                              lolthServoArm);
  ok &= runtime.natives().add(LolthFunctions::SERVO_SET, "SERVO_SET",
                              lolthServoSet);
  ok &= runtime.natives().add(LolthFunctions::SERVO_STATE, "SERVO_STATE",
                              lolthServoState);
  ok &= runtime.natives().add(LolthFunctions::SERVO_DETACH, "SERVO_DETACH",
                              lolthServoDetach);
  ok &= runtime.natives().add(LolthFunctions::SERVO_DETACH_ALL,
                              "SERVO_DETACH_ALL", lolthServoDetachAll);
  ok &= runtime.natives().add(LolthFunctions::DISTANCE_MM, "DISTANCE_MM",
                              lolthDistanceMm);
  ok &= runtime.natives().add(LolthFunctions::SERVO1_WIGGLE,
                              "SERVO1_WIGGLE", lolthServo1Wiggle());
  return ok;
}
