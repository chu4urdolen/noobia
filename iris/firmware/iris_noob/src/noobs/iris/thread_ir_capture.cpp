#include "thread_ir_capture.h"

#include "hw_artifacts.h"
#include "iris_config.h"
#include <services/Esp32IrService.h>
#include <services/Esp32SdMmcService.h>
#include <memory>
#include <new>

namespace {
bool captureFingerprint(uint32_t timestamp, size_t &bytes, uint32_t &hash) {
  const String path = "/samples/ir_raw_" + String(timestamp) + ".csv";
  File input = Esp32SdMmcService::fs().open(path, FILE_READ);
  if (!input) return false;
  String header = input.readStringUntil('\n');
  header.trim();
  if (header != "time_ms,index,level,duration_us" || !input.seek(0)) {
    input.close();
    return false;
  }
  bytes = input.size();
  hash = 2166136261UL;
  size_t checked = 0;
  uint8_t buffer[128];
  while (checked < bytes) {
    const size_t got = input.read(buffer, sizeof(buffer));
    if (!got) break;
    for (size_t index = 0; index < got; ++index) {
      hash ^= buffer[index];
      hash *= 16777619UL;
    }
    checked += got;
  }
  input.close();
  return checked == bytes;
}

class IrisIrCaptureThread final : public NoobThreadProgram {
 public:
  IrisIrCaptureThread() : NoobThreadProgram(1) {}

  NativeResult call(const int32_t *arguments, uint8_t count) override {
    if (count > 1 || (count && (arguments[0] < 1 || arguments[0] > 3600000)))
      return {false, 0, "usage: [duration_ms(1..3600000)]"};
    durationMs_ = count ? uint32_t(arguments[0])
                        : IrisHardware::IR_THREAD_DURATION_MS;
    NativeResult result = NoobThreadProgram::call(nullptr, 0);
    result.detail += " duration_ms=" + String(durationMs_) +
                     " resolution_hz=" +
                     String(Esp32IrService::captureResolutionHz());
    return result;
  }

  NativeResult replayLast(const int32_t *arguments, uint8_t count) {
    if (count > 1 || (count && (arguments[0] < 1 || arguments[0] > 20)))
      return {false, 0, "usage: [repeats(1..20)]"};
    if (!lastPulses_) return {false, 0, "no raw IR capture in memory"};
    NoobThreadProgram::stop();
    NativeResult result = Esp32IrService::replayEnvelope(
        levels_, durationsUs_, lastPulses_, count ? uint8_t(arguments[0]) : 1);
    if (result.ok) result.detail = "source=last_capture " + result.detail;
    return result;
  }

  NativeResult verifyLast(const int32_t *, uint8_t count) {
    if (count) return {false, 0, "usage: no arguments"};
    if (!lastPulses_) return {false, 0, "no raw IR capture in memory"};
    NoobThreadProgram::stop();
    const size_t capacity =
        lastPulses_ + 64 < MAX_PULSES ? lastPulses_ + 64 : MAX_PULSES;
    std::unique_ptr<uint8_t[]> receivedLevels(
        new (std::nothrow) uint8_t[capacity]());
    std::unique_ptr<uint32_t[]> receivedDurations(
        new (std::nothrow) uint32_t[capacity]());
    if (!receivedLevels || !receivedDurations)
      return {false, 0, "insufficient IR comparison memory"};
    NativeResult captured = Esp32IrService::replayAndCapture(
        levels_, durationsUs_, lastPulses_, receivedLevels.get(),
        receivedDurations.get(), capacity);
    if (!captured.ok) return captured;

    const size_t observed = size_t(captured.value);
    if (lastPulses_ > 1024 || observed > 1024)
      return {false, 0, "IR comparison exceeds 1024 pulses"};
    std::unique_ptr<uint16_t[]> rowA(
        new (std::nothrow) uint16_t[observed + 1]());
    std::unique_ptr<uint16_t[]> rowB(
        new (std::nothrow) uint16_t[observed + 1]());
    if (!rowA || !rowB)
      return {false, 0, "insufficient IR alignment memory"};
    auto alignedPulses = [&](uint32_t toleranceUs) {
      uint16_t *previous = rowA.get();
      uint16_t *current = rowB.get();
      for (size_t index = 0; index <= observed; ++index) previous[index] = 0;
      for (size_t source = 0; source < lastPulses_; ++source) {
        current[0] = 0;
        for (size_t target = 0; target < observed; ++target) {
          const uint32_t sourceUs = durationsUs_[source];
          const uint32_t targetUs = receivedDurations[target];
          const uint32_t difference = sourceUs > targetUs
                                          ? sourceUs - targetUs
                                          : targetUs - sourceUs;
          if (levels_[source] == receivedLevels[target] &&
              difference <= toleranceUs)
            current[target + 1] = previous[target] + 1;
          else
            current[target + 1] = previous[target + 1] > current[target]
                                      ? previous[target + 1] : current[target];
        }
        uint16_t *swap = previous;
        previous = current;
        current = swap;
      }
      return previous[observed];
    };
    const uint16_t aligned250 = alignedPulses(250);
    const uint16_t aligned500 = alignedPulses(500);
    uint64_t sourceUs = 0;
    uint64_t receivedUs = 0;
    for (size_t index = 0; index < lastPulses_; ++index)
      sourceUs += durationsUs_[index];
    for (size_t index = 0; index < observed; ++index)
      receivedUs += receivedDurations[index];
    const uint32_t durationDeltaPct = sourceUs
        ? uint32_t((sourceUs > receivedUs ? sourceUs - receivedUs
                                            : receivedUs - sourceUs) * 100 / sourceUs)
        : 0;
    const bool matched = aligned250 * 10 >= lastPulses_ * 9 &&
                         aligned250 * 10 >= observed * 9 &&
                         durationDeltaPct <= 10;
    return {true, matched ? 1 : 0,
            "source_pulses=" + String(lastPulses_) +
                " received_pulses=" + String(observed) +
                " aligned_250us=" + String(aligned250) +
                " aligned_500us=" + String(aligned500) +
                " source_us=" + String(uint32_t(sourceUs)) +
                " received_us=" + String(uint32_t(receivedUs)) +
                " duration_delta_pct=" + String(durationDeltaPct)};
  }

 protected:
  void onStart() override {
    // START is restart-safe when a previous capture is still active.
    Esp32IrService::captureStop();
    startedAt_ = millis();
    frames_ = 0;
    pulses_ = 0;
    lastPulses_ = 0;
    lastMinimumUs_ = 0;
    lastMaximumUs_ = 0;
    lastCarrierHz_ = 0;
    lastStorageError_ = "";
    captureStarted_ = Esp32IrService::captureStart();
  }

  void onStop() override {
    Esp32IrService::captureStop();
    captureStarted_ = false;
  }

  bool step(String &event) override {
    if (!captureStarted_) {
      const String detail = Esp32IrService::captureError();
      NoobThreadProgram::stop();
      event = "NRP/1 0 EVENT IR_CAPTURE_ERROR detail=" + detail;
      return true;
    }
    if (uint32_t(millis() - startedAt_) >= durationMs_) {
      NoobThreadProgram::stop();
      event = "NRP/1 0 EVENT IR_CAPTURE_COMPLETE frames=" + String(frames_) +
              " pulses=" + String(pulses_);
      return true;
    }
    if (!Esp32IrService::captureReady()) return false;

    const size_t count = Esp32IrService::capturePulseCount();
    if (!count || count > MAX_PULSES) {
      NoobThreadProgram::stop();
      event = "NRP/1 0 EVENT IR_CAPTURE_ERROR detail=invalid pulse count";
      return true;
    }
    uint64_t shortDurationSum = 0;
    uint32_t shortDurationCount = 0;
    lastMinimumUs_ = UINT32_MAX;
    lastMaximumUs_ = 0;
    for (size_t index = 0; index < count; ++index) {
      if (!Esp32IrService::capturePulse(index, levels_[index],
                                        durationsUs_[index])) {
        NoobThreadProgram::stop();
        event = "NRP/1 0 EVENT IR_CAPTURE_ERROR detail=pulse copy failed";
        return true;
      }
      if (durationsUs_[index] < lastMinimumUs_)
        lastMinimumUs_ = durationsUs_[index];
      if (durationsUs_[index] > lastMaximumUs_)
        lastMaximumUs_ = durationsUs_[index];
      if (durationsUs_[index] <= 100) {
        shortDurationSum += durationsUs_[index];
        ++shortDurationCount;
      }
    }
    lastPulses_ = count;
    lastCarrierHz_ = shortDurationCount >= 20 && shortDurationSum
                         ? uint32_t(500000ULL * shortDurationCount /
                                    shortDurationSum)
                         : 0;
    const size_t symbols = Esp32IrService::captureSymbolCount();
    const bool full = symbols == Esp32IrService::captureSymbolCapacity();
    NativeResult stored =
        irisStoreIrCapture(levels_, durationsUs_, count, symbols, full);
    // Keep the edge ISR quiescent during SD I/O. The frame is already copied
    // into this thread's buffers, and the next capture starts after storage.
    if (!Esp32IrService::captureRearm()) {
      const String detail = Esp32IrService::captureError();
      NoobThreadProgram::stop();
      event = "NRP/1 0 EVENT IR_CAPTURE_ERROR detail=" + detail;
      return true;
    }
    if (!stored.ok) {
      lastStorageError_ = stored.detail;
      event = "NRP/1 0 EVENT IR_CAPTURE_ERROR detail=" + stored.detail;
      return true;
    }
    ++frames_;
    pulses_ += count;
    NoobRecord record;
    record.add("time_ms", stored.value);
    record.add("pulses", int32_t(count));
    record.add("carrier_est_hz", int32_t(lastCarrierHz_));
    publish(record);
    event = "NRP/1 0 EVENT IR_FRAME time_ms=" + String(stored.value) + " " +
            stored.detail + " min_us=" + String(lastMinimumUs_) +
            " max_us=" + String(lastMaximumUs_) +
            " carrier_est_hz=" + String(lastCarrierHz_);
    return true;
  }

  String statusDetail() const override {
    const uint32_t elapsed = millis() - startedAt_;
    const uint32_t remaining =
        elapsed >= durationMs_ ? 0 : durationMs_ - elapsed;
    return " duration_ms=" + String(durationMs_) +
           " remaining_ms=" + String(remaining) +
           " resolution_hz=" +
           String(Esp32IrService::captureResolutionHz()) +
           " frames=" + String(frames_) + " pulses=" + String(pulses_) +
           " last_pulses=" + String(lastPulses_) +
           " last_min_us=" + String(lastMinimumUs_) +
           " last_max_us=" + String(lastMaximumUs_) +
           " carrier_est_hz=" + String(lastCarrierHz_) +
           " storage_error=" +
           (lastStorageError_.isEmpty() ? String("none") : lastStorageError_);
  }

 private:
  static constexpr size_t MAX_PULSES = Esp32IrService::CAPTURE_MAX_PULSES;
  uint8_t levels_[MAX_PULSES] = {};
  uint32_t durationsUs_[MAX_PULSES] = {};
  uint32_t durationMs_ = IrisHardware::IR_THREAD_DURATION_MS;
  uint32_t startedAt_ = 0;
  uint32_t frames_ = 0;
  uint32_t pulses_ = 0;
  uint32_t lastPulses_ = 0;
  uint32_t lastMinimumUs_ = 0;
  uint32_t lastMaximumUs_ = 0;
  uint32_t lastCarrierHz_ = 0;
  bool captureStarted_ = false;
  String lastStorageError_;
};

IrisIrCaptureThread irThread;
NoobThreadStopFunction irStop(irThread);
NoobThreadStatusFunction irStatus(irThread);
NoobThreadPopFunction irPop(irThread);
NoobThreadPollFunction irPoll(irThread);
NoobThreadFieldFunction irField(irThread);
}

NoobThreadProgram &irisIrThread() { return irThread; }
NoobFunction &irisIrThreadStop() { return irStop; }
NoobFunction &irisIrThreadStatus() { return irStatus; }
NoobFunction &irisIrThreadPop() { return irPop; }
NoobFunction &irisIrThreadPoll() { return irPoll; }
NoobFunction &irisIrThreadField() { return irField; }
NativeResult irisIrReplayLast(const int32_t *arguments, uint8_t count) {
  return irThread.replayLast(arguments, count);
}
NativeResult irisIrVerifyLast(const int32_t *arguments, uint8_t count) {
  return irThread.verifyLast(arguments, count);
}

NativeResult irisIrDictionaryRemember(const String &arguments) {
  int split = arguments.indexOf(' ');
  if (split <= 0 || split >= int(arguments.length()) - 1)
    return {false, 0, "usage: device button"};
  String device = arguments.substring(0, split);
  String button = arguments.substring(split + 1);
  device.trim();
  button.trim();
  auto validLabel = [](const String &label) {
    if (label.isEmpty() || label.length() > 31) return false;
    for (size_t index = 0; index < label.length(); ++index) {
      const char c = label[index];
      if (!isAlphaNumeric(c) && c != '_' && c != '-' && c != '.') return false;
    }
    return true;
  };
  if (!validLabel(device) || !validLabel(button))
    return {false, 0, "labels use letters digits _ - .; maximum 31 chars"};

  NoobRecord record;
  int32_t timestamp = 0;
  if (!irThread.lastPopped(record) || !record.get("time_ms", timestamp))
    return {false, 0, "pop a raw IR capture first"};
  if (!Esp32SdMmcService::ready()) return {false, 0, "SD unavailable"};
  size_t captureBytes = 0;
  uint32_t captureHash = 0;
  if (!captureFingerprint(uint32_t(timestamp), captureBytes, captureHash))
    return {false, 0, "raw IR capture already damaged; dictionary unchanged"};

  fs::FS &storage = Esp32SdMmcService::fs();
  if (!storage.exists("/noob") && !storage.mkdir("/noob"))
    return {false, 0, "cannot create /noob"};
  const char *path = "/noob/ir_dictionary.csv";
  File output = storage.open(path, FILE_APPEND);
  if (!output) return {false, 0, "cannot open IR dictionary"};
  const size_t previousSize = output.size();
  String entry;
  if (!previousSize) entry = "device,button,capture_time_ms\r\n";
  entry += device + "," + button + "," + String(timestamp) + "\r\n";
  const size_t written = output.write(
      reinterpret_cast<const uint8_t *>(entry.c_str()), entry.length());
  output.flush();
  output.close();
  if (written != entry.length())
    return {false, 0, "IR dictionary write incomplete"};
  File verify = storage.open(path, FILE_READ);
  if (!verify || verify.size() != previousSize + entry.length() ||
      !verify.seek(previousSize)) {
    if (verify) verify.close();
    return {false, 0, "IR dictionary verification failed"};
  }
  char tail[128];
  if (entry.length() >= sizeof(tail)) {
    verify.close();
    return {false, 0, "IR dictionary entry too long"};
  }
  const size_t checked = verify.readBytes(tail, entry.length());
  verify.close();
  if (checked != entry.length() || memcmp(tail, entry.c_str(), checked) != 0)
    return {false, 0, "IR dictionary verification failed"};
  size_t afterBytes = 0;
  uint32_t afterHash = 0;
  if (!captureFingerprint(uint32_t(timestamp), afterBytes, afterHash) ||
      afterBytes != captureBytes || afterHash != captureHash)
    return {false, 0, "raw IR capture changed during dictionary write"};
  return {true, timestamp,
          "path=" + String(path) + " device=" + device + " button=" + button,
          record};
}

NativeResult irisIrDictionaryStatus(const int32_t *arguments, uint8_t count) {
  if (count) return {false, 0, "usage: no arguments"};
  if (!Esp32SdMmcService::ready()) return {false, 0, "SD unavailable"};
  const char *path = "/noob/ir_dictionary.csv";
  File input = Esp32SdMmcService::fs().open(path, FILE_READ);
  if (!input) return {true, 0, "path=/noob/ir_dictionary.csv entries=0"};
  uint32_t lines = 0;
  while (input.available()) {
    if (input.read() == '\n') ++lines;
  }
  input.close();
  const uint32_t entries = lines ? lines - 1 : 0;
  return {true, int32_t(entries),
          "path=/noob/ir_dictionary.csv entries=" + String(entries)};
}
