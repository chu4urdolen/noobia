#pragma once

#include "core/noob_program.h"
#include "services/SequenceService.h"

class NoobSequenceProgram : public NoobProgram {
 public:
  NoobSequenceProgram(const SequenceService::ChannelDefinition *channels,
                      uint8_t channelCount)
      : NoobProgram(NoobProgramType::SEQUENCE),
        channels_(channels),
        channelCount_(channelCount) {}
  bool acceptsNumbers() const override { return true; }
  NativeResult call(const int32_t *arguments, uint8_t count) override;
  NativeResult stop() override;

 private:
  const SequenceService::ChannelDefinition *channels_;
  uint8_t channelCount_;
};
