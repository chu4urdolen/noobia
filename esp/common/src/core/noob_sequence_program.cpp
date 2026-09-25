#include "core/noob_sequence_program.h"

NativeResult NoobSequenceProgram::call(const int32_t *arguments,
                                       uint8_t count) {
  if (count > 1 || (count && arguments[0] != 0 && arguments[0] != 1))
    return {false, 0, "usage: [repeat(0|1)]"};
  SequenceService::stop(nullptr, 0);
  NativeResult result = SequenceService::load(channels_, channelCount_);
  if (!result.ok) return result;
  return SequenceService::start(arguments, count);
}

NativeResult NoobSequenceProgram::stop() {
  return SequenceService::stop(nullptr, 0);
}
