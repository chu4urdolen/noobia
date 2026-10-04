#pragma once

#include "core/noob_thread_program.h"

// Periodically calls a native function and queues its structured result.
class NoobSamplingThreadProgram : public NoobThreadProgram {
 public:
  NoobSamplingThreadProgram(uint16_t sourceFunctionId, const char *eventName,
                            uint32_t intervalMs, uint32_t durationMs,
                            const int32_t *sourceArguments = nullptr,
                            uint8_t sourceArgumentCount = 0,
                            const char *sourceAscii = "");
  void begin(NativeRegistry &registry);
  bool acceptsText() const override { return true; }
  NativeResult callText(const String &ascii) override {
    return callMixed(nullptr, 0, ascii);
  }
  NativeResult callMixed(const int32_t *arguments, uint8_t count,
                         const String &ascii) override;
  NativeResult call(const int32_t *arguments, uint8_t count) override;

 protected:
  void onStart() override;
  bool step(String &event) override;
  String statusDetail() const override;

 private:
  static constexpr uint8_t MAX_SOURCE_ARGUMENTS = 4;
  NativeRegistry *registry_ = nullptr;
  NoobProgramChannel source_;
  uint16_t sourceFunctionId_;
  const char *eventName_;
  uint32_t durationMs_;
  uint32_t startedAt_ = 0;
  int32_t sourceArguments_[MAX_SOURCE_ARGUMENTS] = {};
  uint8_t sourceArgumentCount_ = 0;
  String sourceAscii_;
};
