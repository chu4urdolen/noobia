#pragma once

#include <core/noob_thread_program.h>

NoobThreadProgram &irisIrThread();
NoobFunction &irisIrThreadStop();
NoobFunction &irisIrThreadStatus();
NoobFunction &irisIrThreadPop();
NoobFunction &irisIrThreadPoll();
NoobFunction &irisIrThreadField();
NativeResult irisIrReplayLast(const int32_t *arguments, uint8_t count);
NativeResult irisIrVerifyLast(const int32_t *arguments, uint8_t count);
NativeResult irisIrDictionaryRemember(const String &arguments);
NativeResult irisIrDictionaryStatus(const int32_t *arguments, uint8_t count);
