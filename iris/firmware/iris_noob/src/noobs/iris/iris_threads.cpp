#include "iris_threads.h"

#include "iris_config.h"
#include <core/NoobChangeThreadProgram.h>

namespace {
NoobChangeThreadProgram ultrasonicChange(
    IrisFunctions::DISTANCE_MM, "ULTRASONIC_CHANGE",
    IrisHardware::ULTRASONIC_CHANGE_INTERVAL_MS,
    IrisHardware::ULTRASONIC_CHANGE_THRESHOLD_MM,
    IrisHardware::ULTRASONIC_CHANGE_REARM_SAMPLES);
NoobThreadStopFunction ultrasonicChangeStop(ultrasonicChange);
NoobThreadStatusFunction ultrasonicChangeStatus(ultrasonicChange);
NoobThreadPopFunction ultrasonicChangePop(ultrasonicChange);
NoobThreadPollFunction ultrasonicChangePoll(ultrasonicChange);

NoobChangeThreadProgram lightChange(
    IrisFunctions::LIGHT_READ, "LIGHT_CHANGE",
    IrisHardware::LIGHT_CHANGE_INTERVAL_MS,
    IrisHardware::LIGHT_CHANGE_THRESHOLD,
    IrisHardware::LIGHT_CHANGE_REARM_SAMPLES,
    IrisHardware::LIGHT_CHANGE_PAUSE_SEQUENCE_MASK);
NoobThreadStopFunction lightChangeStop(lightChange);
NoobThreadStatusFunction lightChangeStatus(lightChange);
NoobThreadPopFunction lightChangePop(lightChange);
NoobThreadPollFunction lightChangePoll(lightChange);
}

void irisThreadsBegin(NativeRegistry &registry) {
  ultrasonicChange.begin(registry);
  lightChange.begin(registry);
}

NoobThreadProgram &irisUltrasonicChangeThread() {
  return ultrasonicChange;
}
NoobFunction &irisUltrasonicChangeStop() { return ultrasonicChangeStop; }
NoobFunction &irisUltrasonicChangeStatus() { return ultrasonicChangeStatus; }
NoobFunction &irisUltrasonicChangePop() { return ultrasonicChangePop; }
NoobFunction &irisUltrasonicChangePoll() { return ultrasonicChangePoll; }

NoobThreadProgram &irisLightChangeThread() { return lightChange; }
NoobFunction &irisLightChangeStop() { return lightChangeStop; }
NoobFunction &irisLightChangeStatus() { return lightChangeStatus; }
NoobFunction &irisLightChangePop() { return lightChangePop; }
NoobFunction &irisLightChangePoll() { return lightChangePoll; }
