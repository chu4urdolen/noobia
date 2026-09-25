#include "thread_sampling.h"

#include "iris_config.h"
#include <core/noob_sampling_thread.h>

namespace {
NoobSamplingThreadProgram rssiThread(
    IrisFunctions::RSSI_SNAPSHOT, "RSSI_THREAD",
    IrisHardware::RSSI_THREAD_INTERVAL_MS, IrisHardware::RSSI_THREAD_DURATION_MS);
NoobSamplingThreadProgram irThread(
    IrisFunctions::IR_SNAPSHOT, "IR_THREAD", IrisHardware::IR_THREAD_INTERVAL_MS,
    IrisHardware::IR_THREAD_DURATION_MS);
NoobSamplingThreadProgram envThread(
    IrisFunctions::ENV_SNAPSHOT, "ENV_THREAD", IrisHardware::ENV_THREAD_INTERVAL_MS,
    0);

NoobThreadStopFunction rssiStop(rssiThread);
NoobThreadStatusFunction rssiStatus(rssiThread);
NoobThreadPopFunction rssiPop(rssiThread);
NoobThreadPollFunction rssiPoll(rssiThread);
NoobThreadStopFunction irStop(irThread);
NoobThreadStatusFunction irStatus(irThread);
NoobThreadPopFunction irPop(irThread);
NoobThreadPollFunction irPoll(irThread);
NoobThreadStopFunction envStop(envThread);
NoobThreadStatusFunction envStatus(envThread);
NoobThreadPopFunction envPop(envThread);
NoobThreadPollFunction envPoll(envThread);
}

void irisSamplingThreadsBegin(NativeRegistry &registry) {
  rssiThread.begin(registry);
  irThread.begin(registry);
  envThread.begin(registry);
}
NoobThreadProgram &irisRssiThread() { return rssiThread; }
NoobFunction &irisRssiThreadStop() { return rssiStop; }
NoobFunction &irisRssiThreadStatus() { return rssiStatus; }
NoobFunction &irisRssiThreadPop() { return rssiPop; }
NoobFunction &irisRssiThreadPoll() { return rssiPoll; }
NoobThreadProgram &irisIrThread() { return irThread; }
NoobFunction &irisIrThreadStop() { return irStop; }
NoobFunction &irisIrThreadStatus() { return irStatus; }
NoobFunction &irisIrThreadPop() { return irPop; }
NoobFunction &irisIrThreadPoll() { return irPoll; }
NoobThreadProgram &irisEnvThread() { return envThread; }
NoobFunction &irisEnvThreadStop() { return envStop; }
NoobFunction &irisEnvThreadStatus() { return envStatus; }
NoobFunction &irisEnvThreadPop() { return envPop; }
NoobFunction &irisEnvThreadPoll() { return envPoll; }
