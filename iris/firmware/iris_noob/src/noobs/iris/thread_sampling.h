#pragma once

#include <core/noob_thread_program.h>

void irisSamplingThreadsBegin(NativeRegistry &registry);
NoobThreadProgram &irisRssiThread();
NoobFunction &irisRssiThreadStop();
NoobFunction &irisRssiThreadStatus();
NoobFunction &irisRssiThreadPop();
NoobFunction &irisRssiThreadPoll();
NoobFunction &irisRssiThreadField();
NoobThreadProgram &irisEnvThread();
NoobFunction &irisEnvThreadStop();
NoobFunction &irisEnvThreadStatus();
NoobFunction &irisEnvThreadPop();
NoobFunction &irisEnvThreadPoll();
NoobFunction &irisEnvThreadField();
