#include "thread_sampling.h"

#include "iris_config.h"
#include <core/noob_sampling_thread.h>

namespace {
NoobSamplingThreadProgram rssiThread(
    IrisFunctions::RSSI_SNAPSHOT, "RSSI_THREAD",
    IrisHardware::RSSI_THREAD_INTERVAL_MS, IrisHardware::RSSI_THREAD_DURATION_MS);
NoobSamplingThreadProgram envThread(
    IrisFunctions::ENV_SNAPSHOT, "ENV_THREAD", IrisHardware::ENV_THREAD_INTERVAL_MS,
    0);

NoobThreadStopFunction rssiStop(rssiThread);
NoobThreadStatusFunction rssiStatus(rssiThread);
NoobThreadPopFunction rssiPop(rssiThread);
NoobThreadPollFunction rssiPoll(rssiThread);
NoobThreadFieldFunction rssiField(rssiThread);
NoobThreadStopFunction envStop(envThread);
NoobThreadStatusFunction envStatus(envThread);
NoobThreadPopFunction envPop(envThread);
NoobThreadPollFunction envPoll(envThread);
NoobThreadFieldFunction envField(envThread);
}

void irisSamplingThreadsBegin(NativeRegistry &registry) {
  rssiThread.begin(registry);
  envThread.begin(registry);
}
NoobThreadProgram &irisRssiThread() { return rssiThread; }
NoobFunction &irisRssiThreadStop() { return rssiStop; }
NoobFunction &irisRssiThreadStatus() { return rssiStatus; }
NoobFunction &irisRssiThreadPop() { return rssiPop; }
NoobFunction &irisRssiThreadPoll() { return rssiPoll; }
NoobFunction &irisRssiThreadField() { return rssiField; }
NoobThreadProgram &irisEnvThread() { return envThread; }
NoobFunction &irisEnvThreadStop() { return envStop; }
NoobFunction &irisEnvThreadStatus() { return envStatus; }
NoobFunction &irisEnvThreadPop() { return envPop; }
NoobFunction &irisEnvThreadPoll() { return envPoll; }
NoobFunction &irisEnvThreadField() { return envField; }
