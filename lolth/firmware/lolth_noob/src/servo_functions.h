#pragma once

#include <syscalls/noob_native_registry.h>

NoobFunction &lolthServoStepFunction(uint8_t index);
NativeResult lolthServoArm(const int32_t *arguments, uint8_t count);
NativeResult lolthServoSet(const int32_t *arguments, uint8_t count);
NativeResult lolthServoState(const int32_t *arguments, uint8_t count);
NativeResult lolthServoDetach(const int32_t *arguments, uint8_t count);
NativeResult lolthServoDetachAll(const int32_t *arguments, uint8_t count);
