#pragma once

#include <Arduino.h>
#include "protocol/Protocol.h"
#include "vm/NoobVm.h"
#include "syscalls/NativeRegistry.h"
#include "core/CapabilityRegistry.h"

class CommandDispatcher {
 public:
  CommandDispatcher(const char *noobName, const char *firmwareVersion,
                    NoobVm &vm, NativeRegistry &natives,
                    CapabilityRegistry &capabilities);
  String dispatch(const NoobRequest &request);

 private:
  bool decodeHex(const String &text, uint8_t *output, size_t capacity,
                 size_t &length, String &error);
  String callNative(const NoobRequest &request);

  const char *noobName_;
  const char *firmwareVersion_;
  NoobVm &vm_;
  NativeRegistry &natives_;
  CapabilityRegistry &capabilities_;
};
