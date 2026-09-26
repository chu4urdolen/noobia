#pragma once

#include "core/noob_background_service.h"
#include "syscalls/noob_native_registry.h"

namespace SequenceService {
struct ChannelDefinition {
  uint16_t functionId;
  uint32_t intervalMs;
  const uint8_t *bits;
  uint8_t bitCount;
  const int32_t *arguments;
  uint8_t argumentCount;
};

void begin(NativeRegistry &registry);
NativeResult set(const String &arguments);
NativeResult setNumeric(const int32_t *arguments, uint8_t count);
NativeResult load(const ChannelDefinition *channels, uint8_t count);
NativeResult start(const int32_t *arguments, uint8_t count);
NativeResult stop(const int32_t *arguments, uint8_t count);
NativeResult status(const int32_t *arguments, uint8_t count);
NativeResult clear(const int32_t *arguments, uint8_t count);
NativeResult pop(const int32_t *arguments, uint8_t count);
NativeResult queueSize(const int32_t *arguments, uint8_t count);
NativeResult clearQueue(const int32_t *arguments, uint8_t count);
NativeResult field(const int32_t *arguments, uint8_t count);
NativeResult busy(const int32_t *arguments, uint8_t count);
// A bit remains set for the full lifetime of its sequence channel.
uint8_t busyMask();
NoobBackgroundService &backgroundService();
NoobFunction &configurationFunction();
}
