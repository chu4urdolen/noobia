#include "thread_detectors.h"

#include "iris_config.h"
#include <core/noob_change_thread.h>
#include <core/noob_window_rise_thread.h>

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
NoobWindowRiseThreadProgram micRise(
    IrisFunctions::MIC_LEVEL, "MIC_LOUDNESS_RISE",
    IrisHardware::MIC_RISE_SAMPLE_INTERVAL_MS,
    IrisHardware::MIC_RISE_BUCKET_MS, IrisHardware::MIC_RISE_RATIO_PERCENT,
    IrisHardware::MIC_RISE_MINIMUM_RMS,
    IrisHardware::MIC_RISE_REARM_BUCKETS);
NoobThreadStopFunction micRiseStop(micRise);
NoobThreadStatusFunction micRiseStatus(micRise);
NoobThreadPopFunction micRisePop(micRise);
NoobThreadPollFunction micRisePoll(micRise);
NoobThreadStopFunction lightChangeStop(lightChange);
NoobThreadStatusFunction lightChangeStatus(lightChange);
NoobThreadPopFunction lightChangePop(lightChange);
NoobThreadPollFunction lightChangePoll(lightChange);
}

void irisThreadsBegin(NativeRegistry &registry) {
  ultrasonicChange.begin(registry);
  lightChange.begin(registry);
  micRise.begin(registry);
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
NoobThreadProgram &irisMicRiseThread() { return micRise; }
NoobFunction &irisMicRiseStop() { return micRiseStop; }
NoobFunction &irisMicRiseStatus() { return micRiseStatus; }
NoobFunction &irisMicRisePop() { return micRisePop; }
NoobFunction &irisMicRisePoll() { return micRisePoll; }
