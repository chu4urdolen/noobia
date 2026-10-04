#pragma once
// Generated from iris/config/test-policies.json; do not hand-edit.
#include "iris.h"
inline bool irisAddSelfTestPlan(NoobRuntime &runtime) {
  bool ok = true;
  ok &= runtime.selfTest().addProbe("TIME_NOW", 1, nullptr, 0, 1, 0, false, "");
  ok &= runtime.selfTest().addProbe("SEQUENCE_STATUS", 6, nullptr, 0, 1, 0, false, "");
  const int32_t args_9[] = {0};
  ok &= runtime.selfTest().addProbe("SEQUENCE_QUEUE_SIZE", 9, args_9, 1, 1, 0, false, "");
  const int32_t args_11[] = {0};
  ok &= runtime.selfTest().addProbe("SEQUENCE_BUSY", 11, args_11, 1, 1, 0, false, "");
  ok &= runtime.selfTest().addProbe("STORAGE_STATUS", 101, nullptr, 0, 2, 250, false, "");
  ok &= runtime.selfTest().addProbe("WIFI_STATUS", 116, nullptr, 0, 1, 0, false, "");
  ok &= runtime.selfTest().addProbe("MIC_LEVEL", 120, nullptr, 0, 2, 250, false, "");
  const int32_t args_121[] = {0};
  ok &= runtime.selfTest().addProbe("MIC_ABOVE", 121, args_121, 1, 1, 0, false, "");
  ok &= runtime.selfTest().addProbe("VM_LAST_STATUS", 144, nullptr, 0, 1, 0, false, "");
  ok &= runtime.selfTest().addProbe("BLE_STATUS", 162, nullptr, 0, 1, 0, false, "");
  const int32_t args_190[] = {0};
  ok &= runtime.selfTest().addProbe("TEMP_HUMIDITY_READ", 190, args_190, 1, 2, 2500, false, "");
  const int32_t args_191[] = {0, 16};
  ok &= runtime.selfTest().addProbe("ADC_READ", 191, args_191, 2, 2, 250, false, "");
  const int32_t args_192[] = {16};
  ok &= runtime.selfTest().addProbe("LIGHT_READ", 192, args_192, 1, 1, 0, false, "");
  const int32_t args_196[] = {1, 30000};
  ok &= runtime.selfTest().addProbe("ULTRASONIC_READ", 196, args_196, 2, 2, 250, false, "");
  ok &= runtime.selfTest().addProbe("DISTANCE_MM", 199, nullptr, 0, 2, 250, false, "");
  ok &= runtime.selfTest().addProbe("ULTRASONIC_CHANGE_STATUS", 204, nullptr, 0, 1, 0, false, "");
  ok &= runtime.selfTest().addProbe("LIGHT_CHANGE_STATUS", 209, nullptr, 0, 1, 0, false, "");
  ok &= runtime.selfTest().addProbe("MIC_RISE_STATUS", 214, nullptr, 0, 1, 0, false, "");
  ok &= runtime.selfTest().addProbe("RSSI_THREAD_STATUS", 232, nullptr, 0, 1, 0, false, "");
  ok &= runtime.selfTest().addProbe("IR_THREAD_STATUS", 237, nullptr, 0, 1, 0, false, "");
  ok &= runtime.selfTest().addProbe("ENV_THREAD_STATUS", 242, nullptr, 0, 1, 0, false, "");
  const int32_t args_251[] = {0, 32};
  ok &= runtime.selfTest().addProbe("SD_READ", 251, args_251, 2, 2, 250, false, "/noob/runtime_iris.txt");
  ok &= runtime.selfTest().addProbe("NEO_CAPS", 260, nullptr, 0, 3, 10000, true, "");
  ok &= runtime.selfTest().addProbe("NEO_IR_STATUS", 261, nullptr, 0, 1, 0, true, "");
  ok &= runtime.selfTest().addProbe("NEO_FILE_STATUS", 266, nullptr, 0, 1, 0, true, "");
  ok &= runtime.selfTest().addProbe("NEO_DISPLAY_STATUS", 271, nullptr, 0, 1, 0, true, "");
  return ok;
}
