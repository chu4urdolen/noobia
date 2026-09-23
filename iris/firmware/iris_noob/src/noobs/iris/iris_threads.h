#pragma once

#include <core/NoobThreadProgram.h>

void irisThreadsBegin(NativeRegistry &registry);
NoobThreadProgram &irisUltrasonicChangeThread();
NoobFunction &irisUltrasonicChangeStop();
NoobFunction &irisUltrasonicChangeStatus();
NoobFunction &irisUltrasonicChangePop();
NoobFunction &irisUltrasonicChangePoll();
NoobThreadProgram &irisLightChangeThread();
NoobFunction &irisLightChangeStop();
NoobFunction &irisLightChangeStatus();
NoobFunction &irisLightChangePop();
NoobFunction &irisLightChangePoll();
NoobThreadProgram &irisMicRiseThread();
NoobFunction &irisMicRiseStop();
NoobFunction &irisMicRiseStatus();
NoobFunction &irisMicRisePop();
NoobFunction &irisMicRisePoll();
