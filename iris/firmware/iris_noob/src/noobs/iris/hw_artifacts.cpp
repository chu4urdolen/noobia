#include "hw_artifacts.h"

#include "iris_config.h"
#include <services/Esp32CameraService.h>
#include <services/Esp32Dht11Service.h>
#include <services/Esp32IrService.h>
#include <services/Esp32SdMmcService.h>
#include <services/Esp32WifiService.h>
#include <services/MonotonicTimeService.h>
#include <memory>
#include <new>

namespace {
int32_t latestTemperature = 0;
int32_t latestHumidity = 0;
bool haveEnvironment = false;

uint32_t hashBytes(uint32_t hash, const char *bytes, size_t count) {
  for (size_t index = 0; index < count; ++index) {
    hash ^= uint8_t(bytes[index]);
    hash *= 16777619UL;
  }
  return hash;
}

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
  NoobRecord record;
  record.add("time_ms", int32_t(timestamp));
  record.add("networks", scan.value);
  return {true, static_cast<int32_t>(timestamp),
          "path=" + path + " " + scan.detail, record};
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

NativeResult irisStoreIrCapture(const uint8_t *levels,
                                const uint32_t *durationsUs, size_t pulses,
                                size_t symbols, bool full) {
  if (!levels || !durationsUs || !pulses)
    return {false, 0, "empty IR frame"};
  uint32_t timestamp = 0;
  String path;
  if (!artifactPath("/samples", "ir_raw_", ".csv", timestamp, path))
    return {false, 0, "cannot allocate IR capture artifact"};
  File output = Esp32SdMmcService::fs().open(path, FILE_WRITE);
  if (!output) return {false, 0, "cannot create IR capture artifact"};
  // Buffer whole sectors so a capture needs only a few SD writes.
  const char *header = "time_ms,index,level,duration_us";
  uint8_t block[512];
  size_t buffered = 0;
  size_t expected = 0;
  size_t written = 0;
  uint32_t expectedHash = 2166136261UL;
  auto append = [&](const char *data, size_t length) {
    expected += length;
    expectedHash = hashBytes(expectedHash, data, length);
    while (length) {
      const size_t chunk = min(length, sizeof(block) - buffered);
      memcpy(block + buffered, data, chunk);
      buffered += chunk;
      data += chunk;
      length -= chunk;
      if (buffered == sizeof(block)) {
        const size_t count = output.write(block, buffered);
        written += count;
        buffered = 0;
        if (count != sizeof(block)) return false;
      }
    }
    return true;
  };
  if (!append(header, strlen(header)) || !append("\r\n", 2)) {
    output.close();
    return {false, 0, "IR capture header write failed"};
  }
  char row[48];
  for (size_t index = 0; index < pulses; ++index) {
    const int length = snprintf(row, sizeof(row), "%lu,%u,%u,%lu",
                                static_cast<unsigned long>(timestamp),
                                static_cast<unsigned>(index),
                                static_cast<unsigned>(levels[index]),
                                static_cast<unsigned long>(durationsUs[index]));
    if (length <= 0 || length >= int(sizeof(row))) {
      output.close();
      return {false, 0, "IR capture row formatting failed"};
    }
    if (!append(row, size_t(length)) || !append("\r\n", 2)) {
      output.close();
      return {false, 0, "IR capture row write failed"};
    }
  }
  if (buffered) written += output.write(block, buffered);
  output.flush();
  output.close();
  File verify = Esp32SdMmcService::fs().open(path, FILE_READ);
  const size_t actual = verify ? verify.size() : 0;
  uint32_t actualHash = 2166136261UL;
  size_t checked = 0;
  if (verify) {
    uint8_t buffer[64];
    while (checked < actual) {
      const size_t got = verify.read(buffer, sizeof(buffer));
      if (!got) break;
      actualHash = hashBytes(actualHash,
                             reinterpret_cast<const char *>(buffer), got);
      checked += got;
    }
    verify.close();
  }
  if (written != expected || actual != expected || checked != actual ||
      actualHash != expectedHash) {
    return {false, 0, "IR capture verification failed expected=" +
                           String(expected) + " wrote=" + String(written) +
                           " size=" + String(actual) +
                           " checked=" + String(checked) +
                           " checksum=" + String(actualHash) + "/" +
                           String(expectedHash)};
  }
  return {true, static_cast<int32_t>(timestamp),
          "path=" + path + " pulses=" + String(pulses) +
              " symbols=" + String(symbols) +
              " full=" + String(full ? 1 : 0)};
}

NativeResult irisIrReplay(const int32_t *arguments, uint8_t count) {
  if (count < 1 || count > 2 || arguments[0] <= 0 ||
      (count == 2 && (arguments[1] < 1 || arguments[1] > 20)))
    return {false, 0, "usage: timestamp [repeats(1..20)]"};
  const uint8_t repeats = count == 2 ? uint8_t(arguments[1]) : 1;
  const String path =
      "/samples/ir_raw_" + String(uint32_t(arguments[0])) + ".csv";
  File input = Esp32SdMmcService::fs().open(path, FILE_READ);
  if (!input) return {false, 0, "IR capture not found"};
  String header = input.readStringUntil('\n');
  header.trim();
  if (header != "time_ms,index,level,duration_us") {
    input.close();
    return {false, 0, "invalid IR capture header"};
  }
  constexpr size_t MAX_PULSES = Esp32IrService::CAPTURE_MAX_PULSES;
  std::unique_ptr<uint8_t[]> levels(new (std::nothrow) uint8_t[MAX_PULSES]());
  std::unique_ptr<uint32_t[]> durationsUs(
      new (std::nothrow) uint32_t[MAX_PULSES]());
  if (!levels || !durationsUs) {
    input.close();
    return {false, 0, "insufficient IR replay memory"};
  }
  size_t pulses = 0;
  while (input.available() && pulses < MAX_PULSES) {
    String line = input.readStringUntil('\n');
    line.trim();
    if (line.isEmpty()) continue;
    const int first = line.indexOf(',');
    const int second = first < 0 ? -1 : line.indexOf(',', first + 1);
    const int third = second < 0 ? -1 : line.indexOf(',', second + 1);
    if (third < 0) {
      input.close();
      return {false, 0, "invalid IR capture row"};
    }
    if (line.substring(0, first).toInt() != arguments[0] ||
        line.substring(first + 1, second).toInt() != int32_t(pulses)) {
      input.close();
      return {false, 0, "invalid IR capture order"};
    }
    const int32_t level = line.substring(second + 1, third).toInt();
    const int32_t duration = line.substring(third + 1).toInt();
    if ((level != 0 && level != 1) || duration < 1 || duration > 32767) {
      input.close();
      return {false, 0, "invalid IR pulse"};
    }
    levels[pulses] = uint8_t(level);
    durationsUs[pulses] = uint32_t(duration);
    ++pulses;
  }
  const bool overflow = input.available();
  input.close();
  if (overflow) return {false, 0, "IR capture exceeds replay buffer"};
  NativeResult replayed =
      Esp32IrService::replayEnvelope(levels.get(), durationsUs.get(), pulses,
                                    repeats);
  if (replayed.ok) replayed.detail = "path=" + path + " " + replayed.detail;
  return replayed;
}

NativeResult irisIrCaptureInspect(const int32_t *arguments, uint8_t count) {
  if (count < 1 || count > 2 || arguments[0] <= 0 ||
      (count == 2 && arguments[1] < 0))
    return {false, 0, "usage: timestamp [start_index]"};
  const uint32_t timestamp = uint32_t(arguments[0]);
  const uint32_t start = count == 2 ? uint32_t(arguments[1]) : 0;
  const String path = "/samples/ir_raw_" + String(timestamp) + ".csv";
  File input = Esp32SdMmcService::fs().open(path, FILE_READ);
  if (!input) return {false, 0, "IR capture not found"};
  input.readStringUntil('\n');
  String values;
  uint32_t row = 0;
  uint8_t emitted = 0;
  while (input.available() && emitted < 16) {
    String line = input.readStringUntil('\n');
    line.trim();
    if (line.isEmpty()) continue;
    if (row++ < start) continue;
    const int first = line.indexOf(',');
    const int second = first < 0 ? -1 : line.indexOf(',', first + 1);
    const int third = second < 0 ? -1 : line.indexOf(',', second + 1);
    if (third < 0) {
      input.close();
      return {false, 0, "invalid IR capture row"};
    }
    if (emitted) values += ';';
    values += line.substring(first + 1, second);
    values += ':';
    values += line.substring(second + 1, third);
    values += '/';
    values += line.substring(third + 1);
    ++emitted;
  }
  input.close();
  return {true, emitted,
          "path=" + path + " start=" + String(start) + " edges=" + values};
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
    stored.record.add("time_ms", int32_t(timestamp));
    stored.record.add("temperature", temperature);
    stored.record.add("humidity", humidity);
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
