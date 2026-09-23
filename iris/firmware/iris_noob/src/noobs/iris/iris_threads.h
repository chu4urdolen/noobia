#pragma once

#include <core/NoobThreadProgram.h>

void irisThreadsBegin(NativeRegistry &registry);
NoobThreadProgram &irisUltrasonicChangeThread();
NoobFunction &irisUltrasonicChangeStop();
NoobFunction &irisUltrasonicChangeStatus();
NoobFunction &irisUltrasonicChangePop();
