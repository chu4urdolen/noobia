#pragma once

#include "core/NoobThreadProgram.h"

// Turns dynamic changes from any integer-valued native function into events.
class NoobChangeThreadProgram : public NoobThreadProgram {
 public:
  NoobChangeThreadProgram(uint16_t sourceFunctionId, const char *eventName,
                          uint32_t intervalMs, int32_t changeThreshold,
                          uint8_t rearmSamples,
                          uint8_t pauseSequenceChannelMask = 0);
  void begin(NativeRegistry &registry);
  NativeResult call(const int32_t *arguments, uint8_t count) override;

 protected:
  void onStart() override;
  bool step(String &event) override;

 private:
  NativeRegistry *registry_ = nullptr;
  NoobProgramChannel source_;
  uint16_t sourceFunctionId_;
  const char *eventName_;
  int32_t changeThreshold_;
  uint8_t rearmSamples_;
  uint8_t pauseSequenceChannelMask_;
  int32_t previous_ = 0;
  bool havePrevious_ = false;
  bool armed_ = true;
  uint8_t stableSamples_ = 0;
};
