#include "hw_artifacts.h"

#include "iris_config.h"
#include <services/Esp32CameraService.h>
#include <services/Esp32Dht11Service.h>
#include <services/Esp32IrService.h>
#include <services/Esp32SdMmcService.h>
#include <services/Esp32WifiService.h>
#include <services/MonotonicTimeService.h>

namespace {
int32_t latestTemperature = 0;
int32_t latestHumidity = 0;
bool haveEnvironment = false;

bool artifactPath(const char *directory, const char *prefix, const char *suffix,
                  uint32_t &timestamp, String &path) {
  if (!Esp32SdMmcService::ready()) return false;
  fs::FS &storage = Esp32SdMmcService::fs();
  if (!storage.exists(directory) && !storage.mkdir(directory)) return false;
  timestamp = MonotonicTimeService::milliseconds();
  if (!timestamp) timestamp = 1;
  for (uint16_t attempt = 0; attempt < 1000; ++attempt, ++timestamp) {
    path = String(directory) + "/" + prefix + String(timestamp) + suffix;
    if (!storage.exists(path)) return true;
  }
  return false;
}

NativeResult writeRecord(const String &path, const String &header,
                         const String &record, uint32_t timestamp) {
  File output = Esp32SdMmcService::fs().open(path, FILE_WRITE);
  if (!output) return {false, 0, "cannot create artifact"};
  output.println(header);
  output.println(record);
  output.close();
  return {true, static_cast<int32_t>(timestamp), "path=" + path};
}
}

bool irisArtifactsBegin() {
  if (!Esp32SdMmcService::ready()) return false;
  fs::FS &storage = Esp32SdMmcService::fs();
  const bool samples = storage.exists("/samples") || storage.mkdir("/samples");
  const bool metadata = storage.exists("/noob") || storage.mkdir("/noob");
  if (!samples || !metadata) return false;
  File runtime = storage.open("/noob/runtime_iris.txt", FILE_WRITE);
  if (!runtime) return false;
  runtime.println("name=Iris");
  runtime.println("artifact_schema=1");
  runtime.close();
  return true;
}

NativeResult irisCameraSequenceStep(const int32_t *arguments, uint8_t count) {
  if (count != 1 || arguments[0] < 0 || arguments[0] > 1)
    return {false, 0, "usage: enabled(0|1)"};
  if (!arguments[0]) return {true, 0, "skipped=1"};
  uint32_t timestamp = 0;
  String path;
  if (!artifactPath("/captured", "cam_seq_", ".jpg", timestamp, path))
    return {false, 0, "cannot allocate camera artifact"};
  return Esp32CameraService::captureNamed("cam_seq_", timestamp);
}

NativeResult irisIrSequenceStep(const int32_t *arguments, uint8_t count) {
  if (count != 3 || arguments[2] < 0 || arguments[2] > 1)
    return {false, 0, "usage: duration_ms frequency_hz enabled(0|1)"};
  NativeResult sent = Esp32IrService::send(arguments, count);
  if (!sent.ok || !arguments[2]) return sent;
  uint32_t timestamp = 0;
  String path;
  if (!artifactPath("/samples", "ir_tx_", ".csv", timestamp, path))
    return {false, 0, "cannot allocate IR transmit artifact"};
  return writeRecord(path, "time_ms,rx_low_samples,detail",
                     String(timestamp) + "," + String(sent.value) + "," +
                         sent.detail,
                     timestamp);
}

NativeResult irisRssiSnapshot(const int32_t *, uint8_t count) {
  if (count) return {false, 0, "usage: no arguments"};
  uint32_t timestamp = 0;
  String path;
  if (!artifactPath("/samples", "rssi_", ".csv", timestamp, path))
    return {false, 0, "cannot allocate RSSI artifact"};
  NativeResult scan =
      Esp32WifiService::scanToCsv(Esp32SdMmcService::fs(), path);
  if (!scan.ok) return scan;
  return {true, static_cast<int32_t>(timestamp),
          "path=" + path + " " + scan.detail};
}

NativeResult irisIrSnapshot(const int32_t *, uint8_t count) {
  if (count) return {false, 0, "usage: no arguments"};
  const int32_t window[] = {int32_t(IrisHardware::IR_THREAD_WINDOW_MS)};
  NativeResult scan = Esp32IrService::read(window, 1);
  if (!scan.ok) return scan;
  uint32_t timestamp = 0;
  String path;
  if (!artifactPath("/samples", "ir_rx_", ".csv", timestamp, path))
    return {false, 0, "cannot allocate IR receive artifact"};
  return writeRecord(path, "time_ms,edges,detail",
                     String(timestamp) + "," + String(scan.value) + "," +
                         scan.detail,
                     timestamp);
}

NativeResult irisEnvSnapshot(const int32_t *, uint8_t count) {
  if (count) return {false, 0, "usage: no arguments"};
  int32_t temperature = 0;
  int32_t humidity = 0;
  NativeResult sample = Esp32Dht11Service::sample(temperature, humidity);
  if (!sample.ok) return sample;
  uint32_t timestamp = 0;
  String path;
  if (!artifactPath("/samples", "env_", ".csv", timestamp, path))
    return {false, 0, "cannot allocate environment artifact"};
  NativeResult stored = writeRecord(
      path, "time_ms,temperature_tenths_c,humidity_tenths_pct",
      String(timestamp) + "," + String(temperature) + "," + String(humidity),
      timestamp);
  if (stored.ok) {
    latestTemperature = temperature;
    latestHumidity = humidity;
    haveEnvironment = true;
  }
  return stored;
}

NativeResult irisEnvTemperature(const int32_t *, uint8_t count) {
  if (count) return {false, 0, "usage: no arguments"};
  if (!haveEnvironment) return {false, 0, "no environment sample"};
  return {true, latestTemperature, "unit=tenths_c"};
}

NativeResult irisEnvHumidity(const int32_t *, uint8_t count) {
  if (count) return {false, 0, "usage: no arguments"};
  if (!haveEnvironment) return {false, 0, "no environment sample"};
  return {true, latestHumidity, "unit=tenths_pct"};
}
